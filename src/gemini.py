import cv2
import numpy as np


def pee_demo():
    print("=== PEE (菱形預測) 實作演示 ===\n")

    # 1. 讀取圖片
    img = cv2.imread('image/cat.JPG', cv2.IMREAD_GRAYSCALE)
    if img is None:
        print("讀取失敗")
        return

    # 轉為 int32 (非常重要，防止溢位)
    img_process = img.astype(np.int32)
    height, width = img_process.shape

    # 建立一個副本來放結果
    img_stego = img_process.copy()

    # 統計誤差用的變數
    total_de_error = 0
    total_pee_error = 0
    count = 0

    print(f"圖片大小: {height}x{width}")
    print("正在執行菱形預測嵌入 (只處理 '白格子' 像素)...")

    # 2. 掃描圖片 (避開邊界，因為邊界沒有 4 個鄰居)
    for r in range(1, height - 1):
        for c in range(1, width - 1):

            # 【關鍵步驟】西洋棋盤模式 (Checkerboard Pattern)
            # 只有當 (r + c) 是偶數時，我們才處理 (這就是白格子)
            if (r + c) % 2 == 0:

                # --- A. 取得 4 個鄰居 (黑格子，這輪保持不變) ---
                top = img_process[r - 1, c]
                bottom = img_process[r + 1, c]
                left = img_process[r, c - 1]
                right = img_process[r, c + 1]

                # --- B. 計算 PEE 的預測值 (四周平均) ---
                # 這是 PEE 的精髓：利用周圍資訊
                prediction = int((top + bottom + left + right) / 4)

                # 原始值
                original_val = img_process[r, c]

                # --- C. 計算預測誤差 (Prediction Error) ---
                pe = original_val - prediction

                # --- (額外比較) 計算如果是傳統 DE (只看左邊) 的誤差 ---
                de_error = original_val - left

                # 累加絕對值誤差，最後比較誰比較準
                total_pee_error += abs(pe)
                total_de_error += abs(de_error)
                count += 1

                # --- D. 執行嵌入 (公式: e' = 2e + b) ---
                # 假設我們要藏的 bit 是 1
                b = 1

                pe_new = 2 * pe + b

                # --- E. 還原成像素值 ---
                # 新像素 = 預測值 + 新誤差
                val_new = prediction + pe_new

                # 檢查溢位 (簡單跳過策略)
                if 0 <= val_new <= 255:
                    img_stego[r, c] = val_new
                    # 為了演示，我們只印出前幾個點的詳細數據
                    if count < 4:
                        print(f"\n[座標 {r},{c}] 原值: {original_val}")
                        print(f"   -> 鄰居: 上{top} 下{bottom} 左{left} 右{right}")
                        print(f"   -> PEE預測值: {prediction} (誤差: {pe})")
                        print(f"   -> DE 預測值: {left} (誤差: {de_error})")
                        print(f"   -> PEE 擴張後: {val_new}")
                else:
                    # 溢位就保持原值 (真實情況需要記 Map)
                    pass

    # 3. 統計結果分析
    print("\n=== 誤差統計分析 ===")
    print(f"處理像素總數: {count}")
    print(f"DE (只看左邊) 平均誤差絕對值: {total_de_error / count:.2f}")
    print(f"PEE (看四周) 平均誤差絕對值: {total_pee_error / count:.2f}")

    if (total_pee_error < total_de_error):
        print(">> 結論: PEE 預測比較準！誤差越小，擴張後的畫質破壞就越小。")
    else:
        print(">> 結論: 這張圖紋理太亂，兩種差不多。")

    # 4. 顯示圖片
    cv2.imshow('Original', img)
    cv2.imshow('PEE Stego', img_stego.astype(np.uint8))

    print("\n按任意鍵結束...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cv2.imwrite('PEE Stego.jpg', img)


if __name__ == "__main__":
    pee_demo()