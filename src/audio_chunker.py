import os
import re
import subprocess
import tempfile
import imageio_ffmpeg

def get_ffmpeg_cmd():
    return imageio_ffmpeg.get_ffmpeg_exe()

def get_subprocess_flags():
    startupinfo = None
    creation_flags = 0
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creation_flags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0x00004000)
    return startupinfo, creation_flags

def parse_track_lang(filename):
    """Extract language code or identifier from filename."""
    match = re.search(r"_audio_(.+)\.(mp3|m4a|webm|wav|aac)$", filename, re.IGNORECASE)
    if match:
        return match.group(1)
    base = os.path.splitext(filename)[0]
    return base

# --- MP3 frame-boundary byte splitting (DEF-001) ---
# 重新編碼後以 concat -c copy 串接會把 chunk0 尾端填充 + chunk1 編碼器延遲留在接縫 (+1332 samples 靜音)。
# 改為在原始 MP3 的 frame 邊界直接切位元組，合併時直接串接，合併檔與原檔位元級相同。
_MP3_BITRATES = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],   # MPEG-1 Layer III
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],       # MPEG-2/2.5 Layer III
}
_MP3_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}

def _id3v2_size(data):
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
    return size + 10 + (10 if data[5] & 0x10 else 0)

def _mp3_frame_info(data, pos):
    """解析 pos 處的 Layer III frame header，回傳 (frame_len, samples_per_frame, sample_rate)；非合法 header 回傳 None。"""
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    ver = (data[pos + 1] >> 3) & 3
    layer = (data[pos + 1] >> 1) & 3
    br_idx = data[pos + 2] >> 4
    sr_idx = (data[pos + 2] >> 2) & 3
    pad = (data[pos + 2] >> 1) & 1
    if ver == 1 or layer != 1 or br_idx in (0, 15) or sr_idx == 3:
        return None
    sr = _MP3_SAMPLE_RATES[ver][sr_idx]
    br = _MP3_BITRATES[1 if ver == 3 else 2][br_idx] * 1000
    if ver == 3:
        return 144 * br // sr + pad, 1152, sr
    return 72 * br // sr + pad, 576, sr

def _is_vbr_info_frame(data, pos, frame_len):
    """Xing/Info/VBRI 標頭 frame 不含音訊。"""
    return any(tag in data[pos:pos + min(frame_len, 64)] for tag in (b"Xing", b"Info", b"VBRI"))

def mp3_split_offset(data, initial_sec):
    """回傳第一個累計音訊長度 >= initial_sec + 1 frame 的 frame 邊界位元組偏移；檔案短於此則回傳 len(data)。
    多留 1 frame 餘量涵蓋編碼器延遲，確保 chunk0 解碼後至少有 initial_sec 秒。無法解析時拋出 ValueError。"""
    pos = _id3v2_size(data)
    samples = 0
    target = None
    first = True
    while pos < len(data):
        info = _mp3_frame_info(data, pos)
        if info is None:
            if data[pos:pos + 3] == b"TAG":          # 檔尾 ID3v1
                return len(data)
            raise ValueError(f"invalid MP3 frame header at byte {pos}")
        frame_len, spf, sr = info
        if target is None:
            target = int(initial_sec * sr) + spf
        if samples >= target:
            return pos
        if not (first and _is_vbr_info_frame(data, pos, frame_len)):
            samples += spf
        first = False
        pos += frame_len
    return len(data)

def _is_mp3_continuation(path):
    """位元組切割產生的 chunk1 以 frame sync 開頭（或為空）；舊版重新編碼的 chunk 以 ID3 / Info frame 開頭。"""
    with open(path, "rb") as f:
        head = f.read(4096)
    if not head:
        return True
    info = _mp3_frame_info(head, 0)
    return info is not None and not _is_vbr_info_frame(head, 0, info[0])

def split_audio_into_chunks(audio_path, initial_sec=6.0, output_dir=None):
    """
    Splits an audio file into 2 chunks:
      - chunk_0: [0, initial_sec] (for initial instant buffer playback)
      - chunk_1: [initial_sec, end] (for background streaming decode)
    MP3 is split losslessly at a frame boundary (chunk_0 + chunk_1 bytes == original file);
    other formats are re-encoded by ffmpeg.
    Returns:
      (chunk_0_path, chunk_1_path)
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="de_chunk_")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    ext = os.path.splitext(audio_path)[1].lower()
    if not ext:
        ext = ".mp3"

    chunk0_path = os.path.join(output_dir, f"{base_name}_chunk0{ext}")
    chunk1_path = os.path.join(output_dir, f"{base_name}_chunk1{ext}")

    if ext == '.mp3':
        with open(audio_path, 'rb') as f:
            data = f.read()
        try:
            cut = mp3_split_offset(data, initial_sec)
        except ValueError:
            cut = None   # 非標準 MP3：退回 ffmpeg 重新編碼
        if cut is not None:
            with open(chunk0_path, 'wb') as f:
                f.write(data[:cut])
            with open(chunk1_path, 'wb') as f:
                f.write(data[cut:])
            return chunk0_path, chunk1_path

    ffmpeg = get_ffmpeg_cmd()
    startupinfo, creation_flags = get_subprocess_flags()

    # Determine encoder by extension to guarantee clean boundary cutting
    codec_args = ['-c:a', 'copy']
    if ext == '.mp3':
        codec_args = ['-c:a', 'libmp3lame', '-b:a', '192k']
    elif ext in ('.m4a', '.aac'):
        codec_args = ['-c:a', 'aac', '-b:a', '192k']

    # 1. Cut Chunk 0: 0 ~ initial_sec
    cmd0 = [
        ffmpeg, '-y',
        '-i', audio_path,
        '-t', str(initial_sec)
    ] + codec_args + [chunk0_path]

    subprocess.run(
        cmd0,
        capture_output=True,
        startupinfo=startupinfo,
        creationflags=creation_flags,
        check=True
    )

    # 2. Cut Chunk 1: initial_sec ~ end (sample-accurate seeking with -ss after -i)
    cmd1 = [
        ffmpeg, '-y',
        '-i', audio_path,
        '-ss', str(initial_sec)
    ] + codec_args + [chunk1_path]

    subprocess.run(
        cmd1,
        capture_output=True,
        startupinfo=startupinfo,
        creationflags=creation_flags,
        check=True
    )

    return chunk0_path, chunk1_path

def concatenate_chunks(chunk_paths, output_path):
    """
    Seamlessly concatenates multiple audio chunks into a single unified file.
    Uses ffmpeg concat demuxer.
    """
    if not chunk_paths:
        raise ValueError("No chunk paths provided for concatenation.")
    if len(chunk_paths) == 1:
        import shutil
        shutil.copyfile(chunk_paths[0], output_path)
        return output_path

    # MP3 位元組切割的 chunk 直接串接即還原原檔；舊版（重新編碼）的 chunk 仍走 ffmpeg concat 以維持相容
    if os.path.splitext(output_path)[1].lower() == '.mp3' and all(_is_mp3_continuation(p) for p in chunk_paths[1:]):
        with open(output_path, 'wb') as out:
            for p in chunk_paths:
                with open(p, 'rb') as f:
                    out.write(f.read())
        return output_path

    ffmpeg = get_ffmpeg_cmd()
    startupinfo, creation_flags = get_subprocess_flags()

    tmp_list = os.path.join(tempfile.gettempdir(), f"concat_list_{os.getpid()}_{np_hash()}.txt")
    with open(tmp_list, 'w', encoding='utf-8') as f:
        for p in chunk_paths:
            escaped = os.path.abspath(p).replace('\\', '/')
            f.write(f"file '{escaped}'\n")

    try:
        cmd = [
            ffmpeg, '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', tmp_list,
            '-c', 'copy',
            output_path
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            startupinfo=startupinfo,
            creationflags=creation_flags
        )
        if res.returncode != 0:
            # Fallback to re-encoding if stream copy fails
            ext = os.path.splitext(output_path)[1].lower()
            re_codec = ['-c:a', 'libmp3lame'] if ext == '.mp3' else ['-c:a', 'aac']
            cmd_fallback = [
                ffmpeg, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', tmp_list
            ] + re_codec + [output_path]
            subprocess.run(
                cmd_fallback,
                capture_output=True,
                startupinfo=startupinfo,
                creationflags=creation_flags,
                check=True
            )
    finally:
        if os.path.exists(tmp_list):
            try:
                os.remove(tmp_list)
            except Exception:
                pass

    return output_path

def np_hash():
    import random
    return f"{random.randint(100000, 999999)}"
