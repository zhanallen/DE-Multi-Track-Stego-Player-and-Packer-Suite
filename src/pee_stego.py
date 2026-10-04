import cv2
import numpy as np
import struct
import os
import time
import zlib
import json
import imageio_ffmpeg
import subprocess
import re
import tempfile

# Set Numba cache directory to a writable system temp directory to avoid permission errors when running from _internal
numba_temp = os.path.join(tempfile.gettempdir(), "numba_cache")
os.makedirs(numba_temp, exist_ok=True)
os.environ['NUMBA_CACHE_DIR'] = numba_temp

from numba import njit

from audio_chunker import split_audio_into_chunks, concatenate_chunks, parse_track_lang

# Protocol Constants
CHUNK_MAGIC_STREAM = b'DECK'  # Magic header for Chunked Stego Stream
CHUNK_MAGIC_BLOCK  = b'CHNK'  # Magic header for each Chunk block

# ==========================================
# --- 1. 二進制極速向量化轉換 ---
# ==========================================
def files_to_bits(file_paths):
    """
    Packs multiple files into a single bit array (Legacy Monolithic format).
    Structure:
        uint16: number of files
        For each file:
            uint16: filename length
            bytes: filename (utf-8)
            uint32: file content length
            bytes: file content
    Then zlib compresses the entire structure, and prepends the 4-byte payload size header.
    """
    print(f"📦 讀取並封裝多個檔案 (傳統單體模式): {file_paths}")
    payload_body = bytearray()
    
    # 寫入檔案數量
    payload_body.extend(struct.pack('>H', len(file_paths)))
    
    for fp in file_paths:
        filename = os.path.basename(fp)
        fname_bytes = filename.encode('utf-8')
        with open(fp, "rb") as f:
            file_bytes = f.read()
            
        payload_body.extend(struct.pack('>H', len(fname_bytes)) + fname_bytes)
        payload_body.extend(struct.pack('>I', len(file_bytes)) + file_bytes)
        
    compressed_data = zlib.compress(bytes(payload_body), level=9)
    payload_size = len(compressed_data)
    final_data = struct.pack('>I', payload_size) + compressed_data
    
    byte_array = np.frombuffer(final_data, dtype=np.uint8)
    bits_array = np.unpackbits(byte_array)
    
    print(f"  -> 多檔案轉為二進制完畢，總長度: {len(bits_array)} bits ({payload_size} bytes)")
    return bits_array

def files_to_chunked_bits(file_paths, initial_sec=6.0):
    """
    Packs multiple audio files into a chunked streaming bit array with pre-positioned manifest.
    Enables:
      1. Immediate Manifest resolution in Frame 0 (<0.05s) for instant sidebar population.
      2. Initial 3-sec Chunk 0 resolution in Frame 4~8 (<0.3s) for instant audio playback with zero silence.
      3. Background streaming decode for remaining Chunk 1 with instant hot-swapping.
    """
    print(f"⚡ 讀取並以串流切片方式封裝多個音訊 (首塊 {initial_sec}s): {len(file_paths)} 軌")
    temp_cut_dir = tempfile.mkdtemp(prefix="de_chunk_pack_")
    
    try:
        tracks_meta = []
        chunk0_files = []
        chunk1_files = []
        
        for fp in file_paths:
            fname = os.path.basename(fp)
            lang = parse_track_lang(fname)
            ext = os.path.splitext(fp)[1].lower()
            if not ext: ext = ".mp3"
            
            tracks_meta.append({
                "id": lang,
                "filename": fname,
                "ext": ext
            })
            
            # Split into Chunk 0 (0 ~ initial_sec) and Chunk 1 (initial_sec ~ end)
            c0, c1 = split_audio_into_chunks(fp, initial_sec=initial_sec, output_dir=temp_cut_dir)
            chunk0_files.append((lang, fname, ext, c0))
            chunk1_files.append((lang, fname, ext, c1))
            
        # 1. Manifest Block
        manifest_dict = {
            "protocol": "DE_CHUNK_V1",
            "version": 1,
            "initial_sec": float(initial_sec),
            "total_chunks": 2,
            "tracks": tracks_meta
        }
        manifest_json_bytes = json.dumps(manifest_dict, ensure_ascii=False).encode('utf-8')
        manifest_comp = zlib.compress(manifest_json_bytes, level=9)
        manifest_block = CHUNK_MAGIC_STREAM + struct.pack('>HI', 1, len(manifest_comp)) + manifest_comp
        
        # 2. Chunk 0 Block (Initial buffer for all tracks)
        c0_body = bytearray()
        c0_body.extend(struct.pack('>H', len(chunk0_files)))
        for lang, fname, ext, c0_path in chunk0_files:
            lang_bytes = lang.encode('utf-8')
            fname_bytes = fname.encode('utf-8')
            with open(c0_path, 'rb') as f:
                c0_data = f.read()
            c0_body.extend(struct.pack('>H', len(lang_bytes)) + lang_bytes)
            c0_body.extend(struct.pack('>H', len(fname_bytes)) + fname_bytes)
            c0_body.extend(struct.pack('>I', len(c0_data)) + c0_data)
        c0_comp = zlib.compress(bytes(c0_body), level=9)
        chunk0_block = CHUNK_MAGIC_BLOCK + struct.pack('>HBI', 0, 0, len(c0_comp)) + c0_comp
        
        # 3. Chunk 1 Block (Remaining duration for all tracks)
        c1_body = bytearray()
        c1_body.extend(struct.pack('>H', len(chunk1_files)))
        for lang, fname, ext, c1_path in chunk1_files:
            lang_bytes = lang.encode('utf-8')
            fname_bytes = fname.encode('utf-8')
            with open(c1_path, 'rb') as f:
                c1_data = f.read()
            c1_body.extend(struct.pack('>H', len(lang_bytes)) + lang_bytes)
            c1_body.extend(struct.pack('>H', len(fname_bytes)) + fname_bytes)
            c1_body.extend(struct.pack('>I', len(c1_data)) + c1_data)
        c1_comp = zlib.compress(bytes(c1_body), level=9)
        chunk1_block = CHUNK_MAGIC_BLOCK + struct.pack('>HBI', 1, 1, len(c1_comp)) + c1_comp
        
        full_stream_payload = manifest_block + chunk0_block + chunk1_block
        total_payload_size = len(full_stream_payload)
        
        final_data = struct.pack('>I', total_payload_size) + full_stream_payload
        byte_array = np.frombuffer(final_data, dtype=np.uint8)
        bits_array = np.unpackbits(byte_array)
        
        print(f"  -> 切片串流封裝完畢！Manifest ({len(manifest_comp)} B), Chunk0 ({len(c0_comp)} B), Chunk1 ({len(c1_comp)} B)")
        print(f"  -> 總長度: {len(bits_array)} bits ({total_payload_size} bytes)")
        return bits_array
    finally:
        import shutil
        if os.path.exists(temp_cut_dir):
            try:
                shutil.rmtree(temp_cut_dir)
            except Exception:
                pass

def bits_to_bytes(bits_array):
    return np.packbits(bits_array).tobytes()

def decode_multi_files(compressed_bytes, output_dir):
    """
    Unpacks multiple files from decompressed bytes.
    Returns:
        dict: mapping of lang_code/filename -> path of extracted file
    """
    metadata_packed = zlib.decompress(compressed_bytes)
    offset = 0
    
    # 讀取檔案數量
    num_files = struct.unpack('>H', metadata_packed[offset:offset+2])[0]
    offset += 2
    
    extracted_paths = {}
    
    for _ in range(num_files):
        # 讀取檔名長度
        fname_len = struct.unpack('>H', metadata_packed[offset:offset+2])[0]
        offset += 2
        
        # 讀取檔名
        filename = metadata_packed[offset:offset+fname_len].decode('utf-8')
        offset += fname_len
        
        # 讀取檔案內容長度
        file_len = struct.unpack('>I', metadata_packed[offset:offset+4])[0]
        offset += 4
        
        # 讀取檔案內容
        file_bytes = metadata_packed[offset:offset+file_len]
        offset += file_len
        
        output_file_path = os.path.join(output_dir, filename)
        with open(output_file_path, "wb") as f:
            f.write(file_bytes)
            
        # 解析語言代碼
        match = re.search(r"_audio_(.+)\.(mp3|m4a|webm)$", filename)
        if match:
            lang = match.group(1)
            extracted_paths[lang] = output_file_path
        else:
            extracted_paths[filename] = output_file_path
            
    return extracted_paths

# ==========================================
# --- 2. 容量與預測 ---
# ==========================================
def get_payload_size(file_path):
    if isinstance(file_path, (list, tuple)):
        total = 0
        for fp in file_path:
            total += get_payload_size(fp)
        return total
    if not os.path.exists(file_path): return 0
    with open(file_path, "rb") as f: file_bytes = f.read()
    filename = os.path.basename(file_path)
    fname_bytes = filename.encode('utf-8')
    metadata_packed = struct.pack('>H', len(fname_bytes)) + fname_bytes + file_bytes
    return len(zlib.compress(metadata_packed, level=9)) + 4

def estimate_capacity(video_path, sample_size=15):
    if not os.path.exists(video_path): return 0
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened(): return 0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0: return 0

    # Seek to the middle of the video to avoid black intros/outros/credits
    start_frame = 0
    if total_frames > sample_size:
        start_frame = max(0, (total_frames // 2) - (sample_size // 2))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    frames_to_read = min(sample_size, total_frames)
    total_embeddable_bits = 0
    actual_read_count = 0

    for _ in range(frames_to_read):
        ret, frame = cap.read()
        if not ret: break

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray_frame.shape
        G = gray_frame.astype(np.int16)

        # Coltuc 容量 = 不相交 2x2 區塊中「可擴張 (預測誤差 ∈ [-1,1])」的塊數
        # (JPEG4 預測 x̂ = n + w − nw，process band [2,253])
        resv_rows = 2
        sm_buf = np.empty(((h - resv_rows) // 2) * (w // 2), dtype=np.int8)
        _nblocks, nexp = coltuc_classify_numba(G, resv_rows, h, w, sm_buf)
        total_embeddable_bits += nexp
        actual_read_count += 1

    cap.release()
    if actual_read_count == 0: return 0

    avg_bits_per_frame = total_embeddable_bits / actual_read_count
    # 預留每幀 location map 與保留區開銷 (保守抓 ~2KB/幀)，再扣全域標頭
    overhead_per_frame = 16000
    usable = max(0, avg_bits_per_frame - overhead_per_frame)
    return max(0, (int(usable * total_frames) // 8) - 4)

# ==========================================
# --- 3. Numba 極速引擎 ---
# ==========================================
@njit(nogil=True, cache=True)
def pee_embed_core_numba(G, bits_array, bit_idx, total_bits, height, width):
    for i in range(1, height):
        if bit_idx >= total_bits: break
        p_hat = G[i - 1, :]
        p = G[i, :]
        for j in range(width):
            if bit_idx >= total_bits: break
            if not (10 <= p_hat[j] <= 245): continue

            e = p[j] - p_hat[j]
            if -1 <= e <= 1:
                b = bits_array[bit_idx]
                bit_idx += 1
                if e == -1:
                    e_new = -2 + b
                elif e == 0:
                    e_new = b
                elif e == 1:
                    e_new = 2 + b
            elif e > 1:
                e_new = e + 2
            else:
                e_new = e - 2
            G[i, j] = p_hat[j] + e_new
    return bit_idx

@njit(nogil=True, cache=True)
def pee_extract_core_numba(G, bit_buffer, bit_idx, target_bits, height, width, max_possible_bits):
    stop_i = height - 1
    stop_j = width - 1
    finished = False
    error_code = 0

    for i in range(1, height):
        if finished: break
        p_hat = G[i - 1, :]
        p_prime = G[i, :]

        for j in range(width):
            if finished: break
            if not (10 <= p_hat[j] <= 245): continue

            e_p = p_prime[j] - p_hat[j]

            if -2 <= e_p <= 3:
                if e_p == -2 or e_p == 0 or e_p == 2:
                    b = 0
                else:
                    b = 1

                bit_buffer[bit_idx] = b
                bit_idx += 1

                if target_bits == 0 and bit_idx == 32:
                    val_len = 0
                    for k in range(32): val_len = (val_len << 1) | bit_buffer[k]
                    
                    # Zero-Trust safety bounds check for payload memory allocation
                    upper_bound = 400_000_000  # 50MB absolute cap
                    if 0 < max_possible_bits < upper_bound:
                        upper_bound = max_possible_bits
                        
                    if 0 < val_len * 8 <= upper_bound:
                        target_bits = 32 + val_len * 8
                    else:
                        error_code = 1
                        finished = True
                        break

                if target_bits > 0 and bit_idx == target_bits:
                    finished = True
                    stop_i = i
                    stop_j = j
                    break

    if error_code == 0:
        for i in range(stop_i, 0, -1):
            p_hat = G[i - 1, :]
            p_prime = G[i, :]
            start_j = stop_j if i == stop_i else width - 1

            for j in range(start_j, -1, -1):
                if not (10 <= p_hat[j] <= 245): continue

                e_p = p_prime[j] - p_hat[j]
                if -2 <= e_p <= 3:
                    if e_p == -2 or e_p == -1:
                        e = -1
                    elif e_p == 0 or e_p == 1:
                        e = 0
                    elif e_p == 2 or e_p == 3:
                        e = 1
                elif e_p >= 4:
                    e = e_p - 2
                elif e_p <= -4:
                    e = e_p + 2
                else:
                    e = e_p

                G[i, j] = p_hat[j] + e

    return bit_idx, target_bits, finished, error_code

# ==========================================================================
# --- 3b. Coltuc (IEEE TIP 2012) 低失真可逆變換 引擎 ---
#
#   參考文獻: D. Coltuc, "Low Distortion Transform for Reversible
#             Watermarking," IEEE Trans. Image Process., vol.21, no.1,
#             pp.412-417, Jan. 2012.
#
#   相較於上方「北向單像素 PEE」(pee_*_numba)，本引擎實作論文核心：
#     1. JPEG4 預測器       x̂ = n + w − nw  (北 + 西 − 西北)
#     2. 不相交 2x2 區塊上，將擴張後的預測誤差「四等分散」到整個預測脈絡
#        (式 4-5)，使單位元嵌入的方均失真由 ~p² 降至 ~p²/4 (PSNR +4~5dB)。
#     3. process band [2,253]：僅在四個像素皆落於此區間的區塊嵌入，
#        確保每像素變動 ≤ ±1、絕不溢位 (無需 np.clip，嚴格可逆)。
#     4. location map：以「保留前數列像素的 LSB 旁通道」存放壓縮後的
#        skip-map，使解碼端可『確定性』判定每塊 process/skip，
#        徹底消除盲分類在邊界區塊的歧義 → 100% 位元級 (MD5) 還原。
#
#   2x2 區塊布局 (不相交)：
#        nw = Y[r , c ]   n = Y[r , c+1]
#        w  = Y[r+1,c ]   x = Y[r+1,c+1]   ← x 為當前像素
# ==========================================================================
COLTUC_LO = 2
COLTUC_HI = 253

@njit(nogil=True, cache=True)
def coltuc_classify_numba(Y, resv_rows, h, w, sm):
    """掃描 [resv_rows, h) 的不相交 2x2 區塊，填入 skip-map (1=跳過,0=可處理)。
    回傳 (區塊總數, 可擴張區塊數=容量bit)。各區塊獨立，p 值與資料無關。"""
    idx = 0
    nexp = 0
    r = resv_rows
    while r < h - 1:
        c = 0
        while c < w - 1:
            nw = Y[r, c]; n = Y[r, c + 1]; ww = Y[r + 1, c]; x = Y[r + 1, c + 1]
            if (nw < COLTUC_LO or nw > COLTUC_HI or n < COLTUC_LO or n > COLTUC_HI or
                    ww < COLTUC_LO or ww > COLTUC_HI or x < COLTUC_LO or x > COLTUC_HI):
                sm[idx] = 1
            else:
                sm[idx] = 0
                p = x - (n + ww - nw)
                if -1 <= p <= 1:
                    nexp += 1
            idx += 1
            c += 2
        r += 2
    return idx, nexp

@njit(nogil=True, cache=True)
def coltuc_embed_core_numba(Y, sm, stream, total, resv_rows, h, w):
    """把 stream[:total] 嵌入可處理區塊；可擴張塊載 1 bit、其餘平移。回傳已嵌入 bit 數。"""
    cur = 0
    idx = 0
    r = resv_rows
    while r < h - 1 and cur < total:
        c = 0
        while c < w - 1 and cur < total:
            if sm[idx] == 0:
                nw = Y[r, c]; n = Y[r, c + 1]; ww = Y[r + 1, c]; x = Y[r + 1, c + 1]
                xhat = n + ww - nw
                p = x - xhat
                if -1 <= p <= 1:
                    b = stream[cur]; cur += 1
                    P = 2 * p + b
                elif p > 1:
                    P = p + 2
                else:
                    P = p - 2
                d = P - p
                # 四等分 (式4)：u_x,u_w,u_nw,u_n 之和恆為 d，floor 除法
                ux = d // 4; uw = (d + 1) // 4; unw = (d + 2) // 4; un = (d + 3) // 4
                Y[r + 1, c + 1] = x + ux       # X  = x + u_x
                Y[r, c + 1]     = n - un        # N  = n − u_n
                Y[r + 1, c]     = ww - uw       # W  = w − u_w
                Y[r, c]         = nw + unw      # NW = nw + u_nw
            idx += 1
            c += 2
        r += 2
    return cur

@njit(nogil=True, cache=True)
def coltuc_extract_restore_core_numba(Y, sm, stream_out, total, resv_rows, h, w):
    """前向單趟：自可處理區塊提取資料 (P∈[-2,3] 者) 並就地逆變換還原原始像素。
    到達 total bit 即停 (與嵌入端停止點一致)。回傳已提取 bit 數。各 2x2 塊獨立故順序無關。"""
    cur = 0
    idx = 0
    r = resv_rows
    while r < h - 1 and cur < total:
        c = 0
        while c < w - 1 and cur < total:
            if sm[idx] == 0:
                nw = Y[r, c]; n = Y[r, c + 1]; ww = Y[r + 1, c]; x = Y[r + 1, c + 1]
                xhat = n + ww - nw
                P = x - xhat                    # = 2p + b (式6-7)
                if -2 <= P <= 3:
                    stream_out[cur] = P - 2 * (P // 2)   # b = LSB(P)
                    cur += 1
                    p = P // 2
                elif P >= 4:
                    p = P - 2
                else:
                    p = P + 2
                d = P - p
                ux = d // 4; uw = (d + 1) // 4; unw = (d + 2) // 4; un = (d + 3) // 4
                Y[r + 1, c + 1] = x - ux        # 逆 (式9)
                Y[r, c + 1]     = n + un
                Y[r + 1, c]     = ww + uw
                Y[r, c]         = nw - unw
            idx += 1
            c += 2
        r += 2
    return cur

# --- Coltuc 每幀協調器 (Python 端負責 zlib/struct 與 LSB 旁通道) ---
#   保留區 header 布局 (bit 序)：
#     [16b resv_rows][32b 區塊數][32b cmap位元組數][32b 本幀payload bit數][cmap...]
_COLTUC_HDR_BYTES = 14   # 2 + 4 + 4 + 4

def coltuc_embed_frame(frame, Y_size, h, w, bits_array, gpos):
    """於單一 YUV 幀的 Y 平面嵌入全域位元流 bits_array[gpos:] 的一段。
    就地修改 frame。回傳 (新的 gpos, 本幀是否有使用)。"""
    # 1. 決定保留列數與 skip-map (cmap 會隨保留列數微幅變動，迭代收斂)
    resv_rows = 2
    for _ in range(8):
        Y = frame[:Y_size].reshape((h, w)).astype(np.int16)
        sm_buf = np.empty(((h - resv_rows) // 2) * (w // 2), dtype=np.int8)
        nblocks, nexp = coltuc_classify_numba(Y, resv_rows, h, w, sm_buf)
        sm = sm_buf[:nblocks]
        cmap = zlib.compress(np.packbits(sm).tobytes(), 9)
        clen = len(cmap)
        nresv = _COLTUC_HDR_BYTES * 8 + clen * 8
        need_rows = (nresv + w - 1) // w
        if need_rows % 2 == 1:
            need_rows += 1
        if need_rows <= resv_rows:
            break
        resv_rows = need_rows

    capacity = nexp
    if capacity <= nresv + 16:        # 容量連自身保留資料都放不下 → 本幀不用
        return gpos, False

    n_chunk = min(len(bits_array) - gpos, capacity - nresv)

    # 2. 組 header bit，寫入前 nresv 個 Y 像素的 LSB (旁通道)，保存被覆蓋的原始 LSB
    header = struct.pack('>H', resv_rows) + struct.pack('>III', nblocks, clen, n_chunk) + cmap
    map_bits = np.unpackbits(np.frombuffer(header, dtype=np.uint8))
    nresv = len(map_bits)
    yflat = frame[:Y_size]
    saved_lsb = (yflat[:nresv] & 1).copy()
    yflat[:nresv] = (yflat[:nresv] & 0xFE) | map_bits.astype(np.uint8)

    # 3. Coltuc 變換嵌入 (保留列不參與；stream = 被覆蓋LSB + payload段)
    Y = frame[:Y_size].reshape((h, w)).astype(np.int16)
    stream = np.concatenate([saved_lsb.astype(np.uint8), bits_array[gpos:gpos + n_chunk]])
    total = len(stream)
    cur = coltuc_embed_core_numba(Y, sm, stream, total, resv_rows, h, w)
    if cur < total:
        raise ValueError(f"💥 Coltuc 幀容量計算異常：{total - cur} bits 未嵌入")
    # process band [2,253] 保證像素恆在 [0,255]，無需 clip；保留列已含 header 不被覆蓋
    frame[:Y_size] = Y.ravel().astype(np.uint8)
    return gpos + n_chunk, True

def coltuc_decode_frame(frame, Y_size, h, w):
    """自單一 stego 幀提取本幀 payload 段並就地還原 Y 平面。回傳該段 payload bit 陣列。"""
    yflat = frame[:Y_size]
    hb = yflat[:_COLTUC_HDR_BYTES * 8] & 1
    hbytes = np.packbits(hb).tobytes()
    resv_rows = struct.unpack('>H', hbytes[0:2])[0]
    nblocks, clen, n_chunk = struct.unpack('>III', hbytes[2:14])
    nresv = _COLTUC_HDR_BYTES * 8 + clen * 8
    cmap = np.packbits(yflat[_COLTUC_HDR_BYTES * 8:nresv] & 1).tobytes()
    sm = np.unpackbits(np.frombuffer(zlib.decompress(cmap), dtype=np.uint8))[:nblocks].astype(np.int8)

    total = nresv + n_chunk
    Y = frame[:Y_size].reshape((h, w)).astype(np.int16)
    stream_out = np.empty(total, dtype=np.uint8)
    cur = coltuc_extract_restore_core_numba(Y, sm, stream_out, total, resv_rows, h, w)
    if cur < total:
        raise ValueError("💥 Coltuc 幀提取失敗：影片可能已被壓縮失真或非本套件封裝。")

    saved_lsb = stream_out[:nresv]
    payload_chunk = stream_out[nresv:nresv + n_chunk]
    frame[:Y_size] = Y.ravel().astype(np.uint8)            # 寫回還原後像素
    frame[:nresv] = (frame[:nresv] & 0xFE) | saved_lsb     # 還原保留區原始 LSB
    return payload_chunk

# ==========================================
# --- 4. 記憶體管線化多檔案編碼 ---
# ==========================================
def encode_video_multi(video_path, file_paths, output_path, chunked=True, initial_sec=6.0, progress_callback=None):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Carrier video file does not exist: {video_path}")
    if chunked:
        bits_array = files_to_chunked_bits(file_paths, initial_sec=initial_sec)
    else:
        bits_array = files_to_bits(file_paths)
    total_bits = len(bits_array)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    
    frame_size = int(width * height * 1.5)
    Y_size = width * height

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    temp_audio = os.path.join(tempfile.gettempdir(), f"de_temp_audio_{os.getpid()}_{np.random.randint(100000)}.aac")
    
    # Hide console window on Windows
    startupinfo = None
    creation_flags = 0
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        creation_flags = subprocess.CREATE_NO_WINDOW
    
    # 提取影像原有的音軌，維持播放相容性
    subprocess.run([ffmpeg_exe, '-y', '-i', video_path, '-vn', '-c:a', 'aac', '-b:a', '256k', temp_audio],
                   capture_output=True, creationflags=creation_flags, startupinfo=startupinfo)

    # 讀取 YUV420p 管線
    ffmpeg_read_cmd = [
        ffmpeg_exe, '-i', video_path,
        '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-'
    ]
    p_read = subprocess.Popen(
        ffmpeg_read_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        startupinfo=startupinfo
    )

    # 寫入 HEVC 無損 YUV420p 管線 (tag hvc1)
    ffmpeg_cmd = [
        ffmpeg_exe, '-y',
        '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-s', f'{width}x{height}', '-pix_fmt', 'yuv420p', '-r', str(fps),
        '-i', '-'
    ]
    if os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 1024:
        ffmpeg_cmd.extend(['-i', temp_audio, '-c:a', 'copy'])
    ffmpeg_cmd.extend(['-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', 'lossless=1', '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', output_path])

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        startupinfo=startupinfo
    )

    import threading
    from queue import Queue
    read_queue = Queue(maxsize=60)
    write_queue = Queue(maxsize=60)

    def reader():
        while True:
            raw_bytes = p_read.stdout.read(frame_size)
            if not raw_bytes or len(raw_bytes) != frame_size:
                read_queue.put(None)
                break
            frame = np.frombuffer(raw_bytes, dtype=np.uint8).copy()
            read_queue.put(frame)
        p_read.stdout.close()
        p_read.wait()

    def writer():
        while True:
            frame = write_queue.get()
            if frame is None:
                break
            try:
                process.stdin.write(frame.tobytes())
            except Exception:
                pass
        process.stdin.close()

    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=writer, daemon=True).start()

    bit_idx = 0
    frame_count = 0

    while True:
        frame = read_queue.get()
        if frame is None:
            write_queue.put(None)
            break
        frame_count += 1

        if bit_idx < total_bits:
            # Coltuc (TIP 2012) 低失真可逆變換：JPEG4 預測 + 2x2 脈絡分散 + skip-map
            bit_idx, _used = coltuc_embed_frame(frame, Y_size, height, width, bits_array, bit_idx)

        write_queue.put(frame)

        if progress_callback and frame_count % 10 == 0:
            progress_callback(frame_count, total_frames, bit_idx, total_bits)

        if frame_count % 30 == 0: 
            print(f"  -> 已寫入 {frame_count} 幀, 進度 {bit_idx}/{total_bits} bits")

    process.wait()

    if os.path.exists(temp_audio): os.remove(temp_audio)
    if bit_idx < total_bits:
        raise ValueError(f"💥 容量嚴重不足！還有 {total_bits - bit_idx} bits 未寫入。")
    print("🎉 多檔案編碼寫入無損影片成功！")

# ==========================================
# --- 5. 零內存極速解密多檔案 ---
# ==========================================
def decode_video_multi(video_path, output_dir, progress_callback=None, on_manifest_ready=None, on_chunk_ready=None):
    print(f"🔓 啟動 PEE 多檔案解碼還原 (支援串流切片): {video_path}")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    cap = cv2.VideoCapture(video_path)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    frame_size = int(width * height * 1.5)
    Y_size = width * height

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_read_cmd = [
        ffmpeg_exe, '-i', video_path,
        '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-'
    ]
    # Hide console window on Windows
    startupinfo = None
    creation_flags = 0
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        creation_flags = subprocess.CREATE_NO_WINDOW
        
    p_read = subprocess.Popen(
        ffmpeg_read_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        startupinfo=startupinfo
    )

    # 10MB lightweight initial buffer (dynamically resizes up to 50MB or physical limit)
    bit_buffer = np.zeros(80_000_000, dtype=np.uint8)

    bit_idx = 0
    target_bits = 0
    finished_extracting = False

    # Streaming state machine variables
    is_chunked_stream = None # None: pending check, True: chunked protocol, False: legacy
    manifest_resolved = False
    manifest_info = None
    stream_state = "READ_MAGIC"
    chunk_read_offset = 0 # bit index in bit_buffer where current segment/chunk begins
    chunk0_tracks = {}
    full_tracks = {}

    import threading
    from queue import Queue
    read_queue = Queue(maxsize=60)
    stop_event = threading.Event()

    def reader():
        while not stop_event.is_set():
            raw_bytes = p_read.stdout.read(frame_size)
            if not raw_bytes or len(raw_bytes) != frame_size:
                read_queue.put(None)
                break
            frame = np.frombuffer(raw_bytes, dtype=np.uint8).copy()
            read_queue.put(frame)
        p_read.stdout.close()
        try:
            p_read.terminate()
        except:
            pass

    threading.Thread(target=reader, daemon=True).start()

    frame_count = 0
    while True:
        frame = read_queue.get()
        if frame is None:
            break
        frame_count += 1

        # Cooperative yield to prevent 100% CPU starvation of video/audio playback thread
        if frame_count % 8 == 0:
            time.sleep(0.001)

        if not finished_extracting:
            # 🌟 Coltuc 引擎：自本幀提取 payload 段並就地還原像素 (skip-map 確定性判定)
            try:
                payload_chunk = coltuc_decode_frame(frame, Y_size, height, width)
            except Exception as e:
                stop_event.set()
                raise ValueError(f"💥 致命失敗：{e} 影片可能無嵌入資訊或已被壓縮失真！")

            # 累積本幀位元至全域緩衝區
            nchunk = len(payload_chunk)
            if bit_idx + nchunk > len(bit_buffer):
                new_buffer = np.zeros(bit_idx + nchunk + 10_000_000, dtype=np.uint8)
                new_buffer[:bit_idx] = bit_buffer[:bit_idx]
                bit_buffer = new_buffer
            bit_buffer[bit_idx:bit_idx + nchunk] = payload_chunk
            bit_idx += nchunk

            # 一旦集滿 32-bit 長度標頭，計算總目標位元數
            if target_bits == 0 and bit_idx >= 32:
                val_len = 0
                for k in range(32):
                    val_len = (val_len << 1) | int(bit_buffer[k])
                max_possible_bits = total_frames * width * height
                if not (0 < val_len * 8 <= max_possible_bits):
                    stop_event.set()
                    raise ValueError("💥 致命失敗：讀到無效的檔案長度標頭。影片可能無嵌入資訊或已被壓縮失真！")
                target_bits = 32 + val_len * 8
                if target_bits > len(bit_buffer):
                    print(f"🔄 偵測到目標容量 {target_bits} bits，正在動態擴容緩衝區...")
                    new_buffer = np.zeros(target_bits + 10_000_000, dtype=np.uint8)
                    new_buffer[:bit_idx] = bit_buffer[:bit_idx]
                    bit_buffer = new_buffer

            # ⚡ 檢查是否為新版切片串流協議 (前 32 bits 是總長度，第 32~64 bits 是 Magic)
            if is_chunked_stream is None and bit_idx >= 64:
                magic_bytes = np.packbits(bit_buffer[32:64]).tobytes()
                if magic_bytes == CHUNK_MAGIC_STREAM:
                    is_chunked_stream = True
                    stream_state = "READ_MANIFEST_HDR"
                    print("⚡ [串流解碼] 偵測到 DE_CHUNK_V1 切片串流隱寫格式！啟動即時串流管線...")
                else:
                    is_chunked_stream = False
                    print("ℹ️ [串流解碼] 偵測到傳統單體封裝格式，切換至相容全幀解碼模式。")

            # 🚀 切片串流狀態機解析 (邊掃描邊解出 Manifest 與 Chunk 0/1)
            if is_chunked_stream:
                # 1. 讀取 Manifest Header (version: 2B, len: 4B -> 48 bits, offset 64~112)
                if stream_state == "READ_MANIFEST_HDR" and bit_idx >= 112:
                    m_hdr_bytes = np.packbits(bit_buffer[64:112]).tobytes()
                    ver, m_len = struct.unpack('>HI', m_hdr_bytes)
                    m_end_bit = 112 + m_len * 8
                    stream_state = "READ_MANIFEST_BODY"
                    
                # 2. 讀取 Manifest JSON Body
                if stream_state == "READ_MANIFEST_BODY" and bit_idx >= m_end_bit:
                    m_comp_bytes = np.packbits(bit_buffer[112:m_end_bit]).tobytes()
                    m_json = zlib.decompress(m_comp_bytes).decode('utf-8')
                    manifest_info = json.loads(m_json)
                    manifest_resolved = True
                    print(f"🎉 [串流解碼] 第 {frame_count} 幀即時解出語系清冊 Manifest！共 {len(manifest_info.get('tracks', []))} 軌")
                    if on_manifest_ready:
                        try:
                            on_manifest_ready(manifest_info)
                        except Exception as e:
                            print(f"⚠️ on_manifest_ready 回呼異常: {e}")
                    chunk_read_offset = m_end_bit
                    stream_state = "READ_CHUNK_HDR"

                # 3. 讀取 Chunk Header (MAGIC: 4B, idx: 2B, last: 1B, len: 4B -> 11B = 88 bits)
                if stream_state == "READ_CHUNK_HDR" and bit_idx >= chunk_read_offset + 88:
                    hdr_bits = bit_buffer[chunk_read_offset : chunk_read_offset + 88]
                    hdr_bytes = np.packbits(hdr_bits).tobytes()
                    c_magic, c_idx, c_last, c_len = struct.unpack('>4sHBI', hdr_bytes)
                    if c_magic != CHUNK_MAGIC_BLOCK:
                        print(f"⚠️ 預期 CHNK 標頭，實際讀到 {c_magic}，串流提早結束或結束符。")
                        finished_extracting = True
                    else:
                        c_body_end_bit = chunk_read_offset + 88 + c_len * 8
                        stream_state = "READ_CHUNK_BODY"

                # 4. 讀取 Chunk Payload Body
                if stream_state == "READ_CHUNK_BODY" and bit_idx >= c_body_end_bit:
                    chunk_bits = bit_buffer[chunk_read_offset + 88 : c_body_end_bit]
                    c_comp = np.packbits(chunk_bits).tobytes()
                    c_raw = zlib.decompress(c_comp)
                    
                    # 解析該 Chunk 的各軌音訊片段
                    offset = 0
                    num_tracks = struct.unpack('>H', c_raw[offset:offset+2])[0]
                    offset += 2
                    
                    parsed_tracks = []
                    for _ in range(num_tracks):
                        t_len = struct.unpack('>H', c_raw[offset:offset+2])[0]
                        offset += 2
                        lang = c_raw[offset:offset+t_len].decode('utf-8')
                        offset += t_len
                        
                        fn_len = struct.unpack('>H', c_raw[offset:offset+2])[0]
                        offset += 2
                        fname = c_raw[offset:offset+fn_len].decode('utf-8')
                        offset += fn_len
                        
                        data_len = struct.unpack('>I', c_raw[offset:offset+4])[0]
                        offset += 4
                        data_bytes = c_raw[offset:offset+data_len]
                        offset += data_len
                        parsed_tracks.append((lang, fname, data_bytes))

                    extracted_chunk_files = {}
                    if c_idx == 0:
                        for lang, fname, data_bytes in parsed_tracks:
                            ext = os.path.splitext(fname)[1] or ".mp3"
                            out_file = os.path.join(output_dir, f"{lang}_chunk0{ext}")
                            with open(out_file, "wb") as f:
                                f.write(data_bytes)
                            chunk0_tracks[lang] = out_file
                            extracted_chunk_files[lang] = out_file
                    else:
                        from concurrent.futures import ThreadPoolExecutor

                        def _concat_worker(item):
                            t_lang, t_fname, t_data = item
                            ext = os.path.splitext(t_fname)[1] or ".mp3"
                            out_file = os.path.join(output_dir, f"{t_lang}_chunk1{ext}")
                            with open(out_file, "wb") as f:
                                f.write(t_data)
                            full_file = os.path.join(output_dir, f"{t_lang}{ext}")
                            if t_lang in chunk0_tracks:
                                concatenate_chunks([chunk0_tracks[t_lang], out_file], full_file)
                            else:
                                with open(full_file, "wb") as f:
                                    f.write(t_data)
                            return t_lang, full_file

                        max_workers = min(3, os.cpu_count() or 2)
                        with ThreadPoolExecutor(max_workers=max_workers) as pool:
                            for t_lang, full_file in pool.map(_concat_worker, parsed_tracks):
                                full_tracks[t_lang] = full_file
                                extracted_chunk_files[t_lang] = full_file

                    print(f"🎉 [串流解碼] 第 {frame_count} 幀解出 Chunk {c_idx} (共 {len(extracted_chunk_files)} 軌, is_last={bool(c_last)})！")
                    if on_chunk_ready:
                        try:
                            on_chunk_ready(c_idx, extracted_chunk_files, bool(c_last))
                        except Exception as e:
                            print(f"⚠️ on_chunk_ready 回呼異常: {e}")

                    chunk_read_offset = c_body_end_bit
                    if c_last:
                        finished_extracting = True
                    else:
                        stream_state = "READ_CHUNK_HDR"

            if target_bits > 0 and bit_idx >= target_bits:
                finished_extracting = True

            if progress_callback and frame_count % 10 == 0:
                progress_callback(frame_count, total_frames, bit_idx, target_bits)

            if frame_count % 30 == 0:
                print(f"  -> 已掃描 {frame_count} 幀, 提取進度 {bit_idx}/{target_bits} bits")

        if finished_extracting:
            stop_event.set()
            break

    # 回傳最終音軌字典
    if is_chunked_stream:
        final_tracks = full_tracks if full_tracks else chunk0_tracks
        print(f"🎉 串流切片音訊完美還原成功！共解出 {len(final_tracks)} 個多語音軌。")
        return final_tracks
    elif target_bits > 0 and bit_idx >= target_bits:
        payload_bits = bit_buffer[32: target_bits]
        compressed_bytes = bits_to_bytes(payload_bits)
        try:
            print("  -> 進行傳統多檔案 zlib 解壓縮還原...")
            extracted_paths = decode_multi_files(compressed_bytes, output_dir)
            print(f"🎉 逆向多檔案完美還原成功！共還原 {len(extracted_paths)} 個音訊軌。")
            return extracted_paths
        except Exception as e:
            raise ValueError(f"💥 解壓縮解碼失敗：{e}")
    else:
        raise ValueError("💥 致命失敗：無法讀取完整嵌入資訊。")
