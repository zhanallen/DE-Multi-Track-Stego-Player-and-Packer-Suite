import os
import cv2
import filecmp
import numpy as np

# 引入你的藏密核心程式
import stego


def simulate_line_compression(input_video, output_video):
    """
    純 OpenCV 版本的 LINE 壓縮模擬器 (免裝 FFmpeg)
    強制降轉到 720p 並用 mp4v 重新有損編碼
    """
    print("      [模擬器] 啟動 OpenCV 降轉 720p 與二次壓縮模擬...")
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


def auto_tune_all_parameters(video_path, data_path):
    print(f"🚀 開始全自動多變數尋優測試...")
    print(f"目標載體影片: {video_path}")

    temp_encode_path = "temp_encoded.mp4"
    temp_sim_path = "temp_line_sim.mp4"
    temp_decode_data = "temp_decoded.txt"

    # ==========================================
    # 定義搜尋空間 (從小到大，因為我們希望找到最小的可用數值)
    # 你可以自由修改這裡的陣列來擴大或縮小測試範圍
    # ==========================================
    repeat_candidates = [3, 5, 8, 10, 15]  # 測試重複影格數
    delta_candidates = [10, 20, 30, 40, 50]  # 測試強度 Delta

    best_params = None
    found_solution = False

    # 外層迴圈：先測試「重複影格數」
    for r_frames in repeat_candidates:
        if found_solution:
            break  # 如果已經找到最佳解，就提早結束

        # 內層迴圈：再測試「強度 Delta」
        for d_val in delta_candidates:
            print(f"\n==================================================")
            print(f"🧪 正在測試組合: 重複影格 (Frames) = {r_frames} | 強度 (Delta) = {d_val}")

            try:
                # 1. 加密
                print("  [步驟 1] 加密中...")
                stego.robust_encode_h264(video_path, data_path, temp_encode_path,
                                         repeat_frames=r_frames, delta=d_val)

                # 2. 壓縮模擬
                simulate_line_compression(temp_encode_path, temp_sim_path)

                # 3. 解密
                print("  [步驟 3] 嘗試從壓縮影片中解密...")
                stego.robust_decode_h264(temp_sim_path, temp_decode_data, repeat_frames=r_frames)

                # 4. 驗證資料
                if os.path.exists(temp_decode_data):
                    if filecmp.cmp(data_path, temp_decode_data, shallow=False):
                        print(f"  ✅ [大成功] 完美還原資料！這是一組可用的最佳參數。")
                        best_params = {"frames": r_frames, "delta": d_val}
                        found_solution = True
                        break  # 跳出內層迴圈
                    else:
                        print(f"  ❌ [失敗] 資料損毀。代表抵抗力不足，需加強。")
                else:
                    print(f"  ❌ [失敗] 找不到解密檔案。")

            except Exception as e:
                print(f"  ❌ [錯誤] 執行發生異常：{e}")

    # 清理暫存檔
    print("\n清理暫存檔案...")
    for f in [temp_encode_path, temp_sim_path, temp_decode_data]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

    # 輸出最終結果
    print("\n" + "=" * 50)
    if best_params:
        print(f"🎉 尋優大功告成！")
        print(f"🏆 系統為您找到對抗 LINE 壓縮的最佳黃金組合：")
        print(f"   👉 重複影格 (REPEAT_FRAMES) = {best_params['frames']}")
        print(f"   👉 修改強度 (Delta)         = {best_params['delta']}")
        print(f"💡 (建議您將這組參數填入您的 AppUI.py 介面中使用)")
    else:
        print("💀 尋優失敗！這支影片搭配目前的頻率座標，所有組合都全軍覆沒。")
        print("💡 建議處置：請進入 stego.py，將 U1,V1 座標往更低頻調 (例如 1,2)，然後再跑一次腳本。")
    print("=" * 50 + "\n")

    return best_params


if __name__ == "__main__":
    if os.path.exists("./video/input.mp4") and os.path.exists("./file/secret_large.txt"):
        # 執行全自動多變數尋優
        auto_tune_all_parameters("./video/input.mp4", "./file/secret_large.txt")
    else:
        print("請準備 input.mp4 和 secret.txt 進行測試")
