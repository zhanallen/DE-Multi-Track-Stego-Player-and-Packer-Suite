import cv2
import numpy as np
import os
import struct
import sys


def encode_data_to_video(video_path, data_path, output_path):
    # 1. 讀取要隱藏的二進制資料
    with open(data_path, "rb") as f:
        file_bytes = f.read()

    # 加入資料長度檔頭 (4 bytes unsigned int)，以便解碼時知道何時停止
    # 使用 big-endian (>) 格式
    data_length = len(file_bytes)
    full_data = struct.pack('>I', data_length) + file_bytes

    # 將 bytes 轉換為 bits 列表 (0 或 1)
    # 例如 b'a' (97) -> 01100001
    bits = []
    for byte in full_data:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)

    total_bits = len(bits)
    bit_idx = 0

    # 2. 開啟影片
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("無法開啟影片")
        return

    # 取得影片屬性
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # 4. 設定輸出 (關鍵：使用無損編碼 FFV1)
    # 如果系統不支援 FFV1，可嘗試 'HFYU' (HuffYUV)
    fourcc = cv2.VideoWriter_fourcc(*'FFV1')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    print(f"開始寫入資料... 總 bits 數: {total_bits}")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 如果資料已經寫完，剩下的影格直接寫入並跳過處理
        if bit_idx >= total_bits:
            out.write(frame)
            continue

        # 3. 處理影像像素
        # 將 frame 展平以便兩兩處理 (R, G, B 分開視為單一數值)
        # shape 變成 (總像素數, )
        flat_frame = frame.flatten()

        # 我們需要成對的像素，所以長度要是偶數
        limit = len(flat_frame)
        if limit % 2 != 0:
            limit -= 1

        modified = False

        # 兩兩一組遍歷 (步進為 2)
        for i in range(0, limit, 2):
            if bit_idx >= total_bits:
                break

            bit = bits[bit_idx]
            p1 = int(flat_frame[i])
            p2 = int(flat_frame[i + 1])

            # 邏輯核心：
            # bit 1: 左大右小 (p1 > p2)
            # bit 0: 左小右大 (p1 < p2)

            if bit == 1:
                if p1 > p2:
                    pass  # 符合條件
                elif p1 < p2:
                    # 交換
                    flat_frame[i], flat_frame[i + 1] = p2, p1
                else:  # p1 == p2 (相等時無法區分，需強制修改)
                    if p1 > 0:
                        flat_frame[i + 1] = p1 - 1  # 讓右邊變小
                    else:
                        flat_frame[i] = 1  # 讓左邊變大

            else:  # bit == 0
                if p1 < p2:
                    pass  # 符合條件
                elif p1 > p2:
                    # 交換
                    flat_frame[i], flat_frame[i + 1] = p2, p1
                else:  # p1 == p2
                    if p2 > 0:
                        flat_frame[i] = p2 - 1  # 讓左邊變小
                    else:
                        flat_frame[i + 1] = 1  # 讓右邊變大

            bit_idx += 1
            modified = True

        # 將展平的陣列變回原本的形狀 (H, W, 3)
        if modified:
            frame = flat_frame.reshape((height, width, 3))

        out.write(frame)

    cap.release()
    out.release()
    print(f"完成！加密影片已儲存至: {output_path}")

# --- 使用範例 ---
# 為了測試，請確保目錄下有 'input.mp4' 和一個 'secret.txt'
# encode_data_to_video('input.mp4', 'secret.txt', 'output.avi')


def decode_video_to_data(video_path, output_data_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("無法開啟影片")
        return

    print("開始讀取隱藏資料...")

    extracted_bits = []
    data_length = None  # 預計的資料長度 (bytes)
    header_bits_count = 32  # 4 bytes * 8 bits = 32 bits (用來存長度的檔頭)

    stop_reading = False

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret or stop_reading:
            break

        flat_frame = frame.flatten()
        limit = len(flat_frame)
        if limit % 2 != 0:
            limit -= 1

        for i in range(0, limit, 2):
            p1 = int(flat_frame[i])
            p2 = int(flat_frame[i + 1])

            # 判斷邏輯
            # 左 > 右 -> 1
            # 左 < 右 -> 0
            # 左 == 右 -> 資料毀損或非資料區 (這裡視為無效或隨機，但在無損編碼下不應發生)

            if p1 > p2:
                extracted_bits.append(1)
            elif p1 < p2:
                extracted_bits.append(0)
            else:
                # 相等的情況，理論上在 Encode 階段已經處理掉了
                # 如果發生，可能是影片被壓縮過
                extracted_bits.append(0)  # 預設塞 0 避免當機

            # 5. 檢查是否讀完 Header (前 32 bits)
            if data_length is None and len(extracted_bits) >= header_bits_count:
                # 將前 32 bits 轉回整數，取得檔案長度
                header_bits = extracted_bits[:header_bits_count]

                # Bits array to integer
                length_val = 0
                for bit in header_bits:
                    length_val = (length_val << 1) | bit

                data_length = length_val
                print(f"偵測到資料長度: {data_length} bytes")

                # 移除 header bits，只保留資料 bits
                extracted_bits = extracted_bits[header_bits_count:]

            # 檢查是否讀取完畢
            if data_length is not None:
                current_bytes = len(extracted_bits) // 8
                if current_bytes >= data_length:
                    stop_reading = True
                    break

    cap.release()

    # 將 bits 轉回 bytes
    if data_length is not None:
        # 截斷多餘的 bits
        target_bits = extracted_bits[:data_length * 8]

        output_bytes = bytearray()
        for i in range(0, len(target_bits), 8):
            byte_chunk = target_bits[i:i + 8]
            val = 0
            for bit in byte_chunk:
                val = (val << 1) | bit
            output_bytes.append(val)

        with open(output_data_path, "wb") as f:
            f.write(output_bytes)
        print(f"資料解密完成，已存至: {output_data_path}")
    else:
        print("無法讀取有效的資料檔頭，可能影片未包含資料或格式已被破壞。")

# --- 使用範例 ---
# decode_video_to_data('output.avi', 'restored_secret.txt')

if __name__ == "__main__":
    # 建立測試檔案
    with open("secret.txt", "w") as f:
        f.write("Hello! This is a secret message hidden in video pixels.")

    print("--- 步驟 1: 加密 ---")
    # 確保你有 input.mp4
    if not os.path.exists("input.mp4"):
        print("錯誤：找不到 input.mp4，請先準備一個影片檔案。")
    else:
        encode_data_to_video("input.mp4", "secret.txt", "output.mp4")

        print("\n--- 步驟 2: 解密 ---")
        decode_video_to_data("output.mp4", "restored_secret.txt")

        # 驗證內容
        if os.path.exists("restored_secret.txt"):
            with open("restored_secret.txt", "r") as f:
                print(f"\n還原的內容: {f.read()}")