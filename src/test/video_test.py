import cv2
import numpy as np
import struct
import os


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


# --- 1. 加密程式 (加入 repeat_frames 與 delta 參數) ---
# --- 優化版 stego.py 的加密部分 (其他函式如 text_to_bits 不變) ---

def robust_encode_h264(video_path, data_path, output_path, repeat_frames=10, delta=5):
    bits = text_to_bits(data_path)
    total_bits = len(bits)
    bit_idx = 0

    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # 🌟 核心：依然使用動態 BLOCK_SIZE 對抗縮放 (建議原本高度 // 90, BLOCK_SIZE=12效果較好)
    BLOCK_SIZE = height // 90
    if BLOCK_SIZE < 4: BLOCK_SIZE = 4  # 防呆

    cols = width // (BLOCK_SIZE * 2)
    rows = height // BLOCK_SIZE
    bits_per_frame = cols * rows

    print(f"影片解析度: {width}x{height} (動態 BLOCK_SIZE: {BLOCK_SIZE})")
    print(f"抗壓縮強度: {delta}, 重複幀數: {repeat_frames}")

    # 使用 MP4 編碼
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_buffer = []

    # 🌟 新增：時間漸變權重 (Temporal Fading Mask)
    # 建立一個像呼吸燈一樣的權重陣列，例如 [0.1, 0.4, 0.8, 1.0, 1.0, 0.8, 0.4, 0.1]
    temporal_mask = np.ones(repeat_frames)
    fade_len = max(1, repeat_frames // 3)  # 漸變長度
    for i in range(fade_len):
        weight = (i + 1) / (fade_len + 1)
        temporal_mask[i] = weight  # 開頭漸強
        temporal_mask[-(i + 1)] = weight  # 結尾漸弱

    while True:
        ret, frame = cap.read()
        if not ret:
            if frame_buffer:
                for f in frame_buffer: out.write(f)
            break

        frame_buffer.append(frame)

        # 當收集滿 repeat_frames 張影格，開始寫入
        if len(frame_buffer) == repeat_frames:
            start_bit_idx = bit_idx
            temp_bit_idx = start_bit_idx

            # 🌟 關鍵 1：我們以這批影格的「第一張」作為基準，計算出「一張」專屬的亮度修改圖
            base_frame = cv2.cvtColor(frame_buffer[0], cv2.COLOR_BGR2YUV)
            base_y = base_frame[:, :, 0].astype(np.float32)

            # 建立一張全黑的空白畫布，用來畫我們要修改的差值
            diff_map = np.zeros_like(base_y, dtype=np.float32)

            for r in range(rows):
                for c in range(cols):
                    if temp_bit_idx >= total_bits:
                        break

                    bit = bits[temp_bit_idx]

                    x1 = c * (BLOCK_SIZE * 2)
                    y1 = r * BLOCK_SIZE
                    x2 = x1 + BLOCK_SIZE

                    block_L = base_y[y1:y1 + BLOCK_SIZE, x1:x1 + BLOCK_SIZE]
                    block_R = base_y[y1:y1 + BLOCK_SIZE, x2:x2 + BLOCK_SIZE]

                    mean_L = np.mean(block_L)
                    mean_R = np.mean(block_R)

                    # 恢復正確的自適應邏輯：確保修改後一定能解碼！
                    if bit == 1:
                        if mean_L < mean_R + delta:
                            diff = (mean_R + delta - mean_L) / 2 + delta
                            diff_map[y1:y1 + BLOCK_SIZE, x1:x1 + BLOCK_SIZE] += diff
                            diff_map[y1:y1 + BLOCK_SIZE, x2:x2 + BLOCK_SIZE] -= diff
                    else:
                        if mean_R < mean_L + delta:
                            diff = (mean_L + delta - mean_R) / 2 + delta
                            diff_map[y1:y1 + BLOCK_SIZE, x1:x1 + BLOCK_SIZE] -= diff
                            diff_map[y1:y1 + BLOCK_SIZE, x2:x2 + BLOCK_SIZE] += diff

                    temp_bit_idx += 1

            # 🌟 關鍵 2：對這張修改圖進行高斯模糊，消除方塊的「硬邊緣」，變成柔和的雲霧狀
            blur_size = int(BLOCK_SIZE * 1.5)
            if blur_size % 2 == 0: blur_size += 1
            if blur_size < 3: blur_size = 3
            smoothed_diff = cv2.GaussianBlur(diff_map, (blur_size, blur_size), 0)

            # 🌟 關鍵 3：將這張「柔和且固定」的修改圖，套用到這 10 張影格上 (避免閃爍)
            for frame_idx in range(repeat_frames):
                current_frame = frame_buffer[frame_idx]
                yuv_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2YUV)
                y_channel = yuv_frame[:, :, 0].astype(np.float32)

                # 疊加並限制範圍
                y_channel = np.clip(y_channel + smoothed_diff, 0, 255)

                yuv_frame[:, :, 0] = y_channel.astype(np.uint8)
                frame_buffer[frame_idx] = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2BGR)

            # 寫入修改後的這批影格
            for f in frame_buffer:
                out.write(f)

            # 清空 buffer，更新 bit 進度
            frame_buffer = []
            bit_idx = temp_bit_idx

    cap.release()
    out.release()
    print(f"加密完成：{output_path}")


# --- 解密程式 robust_decode_h264 不需要大幅修改，因為它是計算平均值，時間漸變只會輕微影響平均亮度，不影響正負判斷 ---


# --- 2. 解密程式 (加入 repeat_frames 參數) ---
def robust_decode_h264(video_path, output_data_path, repeat_frames=5):
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    BLOCK_SIZE = height // 90
    if BLOCK_SIZE < 2: BLOCK_SIZE = 2

    cols = width // (BLOCK_SIZE * 2)
    rows = height // BLOCK_SIZE

    extracted_bits = []
    frame_buffer = []
    data_length = None
    header_parsed = False

    while True:
        ret, frame = cap.read()
        if not ret: break
        frame_buffer.append(frame)

        if len(frame_buffer) == repeat_frames:
            diff_accumulator = np.zeros((rows, cols))

            for f in frame_buffer:
                yuv = cv2.cvtColor(f, cv2.COLOR_BGR2YUV)
                y_channel = yuv[:, :, 0]

                for r in range(rows):
                    for c in range(cols):
                        x1 = c * (BLOCK_SIZE * 2)
                        y1 = r * BLOCK_SIZE
                        x2 = x1 + BLOCK_SIZE

                        block_L = y_channel[y1:y1 + BLOCK_SIZE, x1:x1 + BLOCK_SIZE]
                        block_R = y_channel[y1:y1 + BLOCK_SIZE, x2:x2 + BLOCK_SIZE]

                        diff = np.mean(block_L) - np.mean(block_R)
                        diff_accumulator[r, c] += diff

            for r in range(rows):
                for c in range(cols):
                    if header_parsed and data_length is not None:
                        if len(extracted_bits) >= data_length * 8: continue

                    final_diff = diff_accumulator[r, c]
                    if final_diff > 0:
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
    else:
        raise ValueError("解密失敗：無法解析有效的檔頭。可能參數設定錯誤或影片被過度壓縮。")


# --- 測試 ---
if __name__ == "__main__":
    # 建立測試資料
    with open("secret_large.txt", "w") as f:
        f.write("This is a robust test message that should survive H.264 compression! " * 100)

    if os.path.exists("input.mp4"):
        # 1. 加密
        # robust_encode_h264("input.mp4", "secret_large.txt", "output_h264.mp4")

        # 2. 解密
        robust_decode_h264("line.mp4", "restored_large.txt")

        # 3. 驗證
        if os.path.exists("restored_large.txt"):
            with open("restored_large.txt", "r", errors='ignore') as f:
                print("\n[還原內容]:", f.read()[:100], "...")
    else:
        print("請準備 input.mp4")