import os
import cv2
import filecmp
import shutil
import numpy as np

import stego


def simulate_line_compression(input_video, output_video):
    """純 OpenCV 版本的降轉與二次壓縮模擬"""
    cap = cv2.VideoCapture(input_video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps): fps = 30.0

    target_w, target_h = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video, fourcc, fps, (target_w, target_h))

    while True:
        ret, frame = cap.read()
        if not ret: break
        resized_frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
        out.write(resized_frame)

    cap.release()
    out.release()


def run_frequency_visual_test(video_path, data_path):
    print("🎬 開始【頻率與視覺效果】自動化對比實驗...")

    # 你已經確認的好參數
    fixed_frames = 3

    # 我們要測試的 Delta 範圍 (從小到大，尋找破壞最小的點)
    delta_candidates = range(10, 81, 10)

    # 準備我們要測試的不同頻率帶 (座標, 名稱)
    test_frequencies = [
        ((1, 2), (2, 1), "01_超低頻"),
        ((2, 3), (3, 2), "02_低頻"),
        ((3, 4), (4, 3), "03_中低頻"),
        ((4, 5), (5, 4), "04_中頻"),
        ((5, 6), (6, 5), "05_中高頻")
    ]

    temp_encode = "temp_enc.mp4"
    temp_sim = "temp_sim.mp4"
    temp_dec = "temp_dec.txt"

    # 建立一個資料夾來存放實驗結果
    output_dir = "Visual_Test_Results"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"📁 實驗產出的影片將會存放在 [{output_dir}] 資料夾中\n")

    for freq_pair in test_frequencies:
        (u1, v1), (u2, v2), freq_name = freq_pair
        print(f"==================================================")
        print(f"📡 正在測試頻段: {freq_name} (座標: {u1},{v1} vs {u2},{v2})")

        success = False

        for d_val in delta_candidates:
            print(f"   ▶ 嘗試 Delta = {d_val} ...", end=" ")

            try:
                # 加密
                stego.robust_encode_h264(video_path, data_path, temp_encode,
                                         repeat_frames=fixed_frames, delta=d_val,
                                         u1=u1, v1=v1, u2=u2, v2=v2)

                # 壓縮
                simulate_line_compression(temp_encode, temp_sim)

                # 解密
                stego.robust_decode_h264(temp_sim, temp_dec,
                                         repeat_frames=fixed_frames,
                                         u1=u1, v1=v1, u2=u2, v2=v2)

                # 驗證
                if os.path.exists(temp_dec) and filecmp.cmp(data_path, temp_dec, shallow=False):
                    print("✅ 成功存活！")

                    # 存檔這個成功的影片
                    final_video_name = f"{freq_name}_Delta{d_val}.mp4"
                    final_path = os.path.join(output_dir, final_video_name)
                    shutil.copy(temp_encode, final_path)  # 拷貝加密後(未壓縮前)的影片供你觀察

                    print(f"   💾 已將此頻段最佳影片存為: {final_path}")
                    success = True
                    break  # 這個頻率找到最小 Delta 了，換下一個頻率
                else:
                    print("❌ 被壓縮破壞。")

            except Exception as e:
                print(f"⚠️ 發生錯誤 ({e})")

        if not success:
            print(f"   💀 結論：{freq_name} 在最高 Delta={max(delta_candidates)} 下依然全軍覆沒，無法抵抗壓縮。")

    # 清理暫存
    for f in [temp_encode, temp_sim, temp_dec]:
        if os.path.exists(f): os.remove(f)

    print("\n🎉 實驗結束！請前往 Visual_Test_Results 資料夾，用肉眼比較不同頻段的畫面變化吧！")


if __name__ == "__main__":
    if os.path.exists("./video/input.mp4") and os.path.exists("./file/secret_large.txt"):
        run_frequency_visual_test("./video/input.mp4", "./file/secret_large.txt")
    else:
        print("請準備 input.mp4 和 secret.txt 進行測試")