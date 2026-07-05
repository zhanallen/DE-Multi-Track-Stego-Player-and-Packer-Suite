import cv2
import numpy as np
import struct
import os

# --- 全域參數設定 ---
NORM_WIDTH = 1280
NORM_HEIGHT = 720
BLOCK_SIZE = 16


def text_to_bits(file_path):
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    length = len(file_bytes)
    full_data = struct.pack('>I', length) + file_bytes
    bits = []
    for byte in full_data:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
    return bits


def bits_to_bytes(bits):
    bytes_list = bytearray()
    for i in range(0, len(bits), 8):
        byte_chunk = bits[i:i + 8]
        if len(byte_chunk) < 8: break
        val = 0
        for bit in byte_chunk:
            val = (val << 1) | bit
        bytes_list.append(val)
    return bytes_list


# --- 1. 空間投票版：加密程式 ---
# 新增參數 spatial_repeat=3 (一個 Bit 寫入 3 個區塊)
def robust_encode_h264(video_path, data_path, output_path, repeat_frames=3, delta=30, u1=4, v1=5, u2=5, v2=4,
                       spatial_repeat=3):
    bits = text_to_bits(data_path)
    total_bits = len(bits)
    bit_idx = 0

    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    cols = NORM_WIDTH // BLOCK_SIZE
    rows = NORM_HEIGHT // BLOCK_SIZE
    blocks_per_frame = cols * rows

    # 🌟 因為空間重複，每批影格能藏的實際位元數會除以 spatial_repeat
    bits_per_batch = blocks_per_frame // spatial_repeat

    print(f"原始解析度: {width}x{height} | 內部畫布: {NORM_WIDTH}x{NORM_HEIGHT}")
    print(f"每批影格可藏: {bits_per_batch} bits (空間重複 {spatial_repeat} 次) | 總資料: {total_bits} bits")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_buffer = []

    while True:
        ret, frame = cap.read()
        if not ret:
            if frame_buffer:
                for f in frame_buffer: out.write(f)
            break

        frame_buffer.append(frame)

        if len(frame_buffer) == repeat_frames:
            start_bit_idx = bit_idx

            for frame_idx in range(repeat_frames):
                current_frame = frame_buffer[frame_idx]
                yuv_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2YUV)

                original_y = yuv_frame[:, :, 0]
                norm_y = cv2.resize(original_y, (NORM_WIDTH, NORM_HEIGHT), interpolation=cv2.INTER_CUBIC)
                norm_y_float = np.float32(norm_y)

                for r in range(rows):
                    for c in range(cols):
                        # 🌟 計算目前走到第幾個區塊
                        block_idx = r * cols + c

                        # 🌟 核心：每 spatial_repeat 個區塊，共用同一個 bit_idx
                        current_bit_idx = start_bit_idx + (block_idx // spatial_repeat)

                        if current_bit_idx >= total_bits:
                            break

                        bit = bits[current_bit_idx]
                        x = c * BLOCK_SIZE
                        y = r * BLOCK_SIZE

                        block = norm_y_float[y:y + BLOCK_SIZE, x:x + BLOCK_SIZE]
                        dct_block = cv2.dct(block)

                        val1 = dct_block[u1, v1]
                        val2 = dct_block[u2, v2]

                        if bit == 1:
                            if val1 < val2 + delta:
                                diff = (val2 + delta - val1) / 2 + delta
                                dct_block[u1, v1] += diff
                                dct_block[u2, v2] -= diff
                        else:
                            if val2 < val1 + delta:
                                diff = (val1 + delta - val2) / 2 + delta
                                dct_block[u2, v2] += diff
                                dct_block[u1, v1] -= diff

                        idct_block = cv2.idct(dct_block)
                        norm_y_float[y:y + BLOCK_SIZE, x:x + BLOCK_SIZE] = idct_block

                modified_y = cv2.resize(norm_y_float, (width, height), interpolation=cv2.INTER_CUBIC)
                yuv_frame[:, :, 0] = np.clip(modified_y, 0, 255).astype(np.uint8)
                frame_buffer[frame_idx] = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2BGR)

            for f in frame_buffer:
                out.write(f)

            frame_buffer = []

            # 🌟 更新總進度 (加上這批實際處理的位元數)
            bit_idx += bits_per_batch
            if bit_idx >= total_bits:
                print("資料寫入完畢，剩餘影格直接複製...")
                while True:
                    ret, frame = cap.read()
                    if not ret: break
                    out.write(frame)
                break

    cap.release()
    out.release()
    print(f"加密完成：{output_path}")


# --- 2. 空間投票版：解密程式 ---
def robust_decode_h264(video_path, output_data_path, repeat_frames=3, u1=4, v1=5, u2=5, v2=4, spatial_repeat=3):
    cap = cv2.VideoCapture(video_path)

    cols = NORM_WIDTH // BLOCK_SIZE
    rows = NORM_HEIGHT // BLOCK_SIZE
    blocks_per_frame = cols * rows

    extracted_bits = []
    frame_buffer = []
    data_length = None
    header_parsed = False

    while True:
        ret, frame = cap.read()
        if not ret: break
        frame_buffer.append(frame)

        if len(frame_buffer) == repeat_frames:
            # 🌟 改用一維陣列來累積所有的區塊差異值，方便後續分組
            diff_accumulator = np.zeros(blocks_per_frame)

            for f in frame_buffer:
                yuv = cv2.cvtColor(f, cv2.COLOR_BGR2YUV)
                original_y = yuv[:, :, 0]
                norm_y = cv2.resize(original_y, (NORM_WIDTH, NORM_HEIGHT), interpolation=cv2.INTER_CUBIC)
                norm_y_float = np.float32(norm_y)

                for r in range(rows):
                    for c in range(cols):
                        block_idx = r * cols + c
                        x = c * BLOCK_SIZE
                        y = r * BLOCK_SIZE

                        block = norm_y_float[y:y + BLOCK_SIZE, x:x + BLOCK_SIZE]
                        dct_block = cv2.dct(block)

                        diff = dct_block[u1, v1] - dct_block[u2, v2]
                        diff_accumulator[block_idx] += diff

            # 🌟 核心：分組進行「軟投票」
            # 每次跳 spatial_repeat 步來讀取一個群組
            for i in range(0, blocks_per_frame - spatial_repeat + 1, spatial_repeat):
                if header_parsed and data_length is not None:
                    if len(extracted_bits) >= data_length * 8: continue

                # 將這群組內的差異值加總 (能量聚合)
                group_diff = np.sum(diff_accumulator[i: i + spatial_repeat])

                if group_diff > 0:
                    extracted_bits.append(1)
                else:
                    extracted_bits.append(0)

            frame_buffer = []

            if not header_parsed and len(extracted_bits) >= 32:
                header_bits = extracted_bits[:32]
                val = 0
                for bit in header_bits:
                    val = (val << 1) | bit
                data_length = val

                if 0 < data_length < 10000000:
                    extracted_bits = extracted_bits[32:]
                    header_parsed = True
                else:
                    data_length = None

            if header_parsed and len(extracted_bits) >= data_length * 8:
                break

    cap.release()

    if header_parsed:
        final_bytes = bits_to_bytes(extracted_bits[:data_length * 8])
        with open(output_data_path, "wb") as f:
            f.write(final_bytes)
        print(f"解密成功！檔案已存為 {output_data_path}")
    else:
        raise ValueError("解密失敗：無法解析有效的檔頭。可能參數設定錯誤或影片被過度壓縮。")