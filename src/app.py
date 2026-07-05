import cv2
import numpy as np

# 1. 讀取圖片 (轉為灰階)
# 參數 0 或 cv2.IMREAD_GRAYSCALE 代表以灰階模式讀取
img_path = 'image/cat.JPG'  # 請確保資料夾有這張圖片，或換成你的路徑
img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
img_Original = img.copy()
cv2.imshow('Original', img_Original)

# 檢查是否讀取成功
if img is None:
    print("讀取失敗，請檢查圖片路徑")
    exit()

# 顯示圖片的基本資訊
print(f"圖片尺寸: {img.shape}") # (高度 height, 寬度 width)
print(f"資料型態: {img.dtype}") # 通常是 uint8

# def hide_data(img, data):
img_height, img_width = img.shape

img = img.astype(np.int32)
for r in range(img_height):
    for c in range(0, img_width, 2):
        x = img[r, c]
        y = img[r, c+1]
        l = (x+y)//2
        h = x - y
        b = 1
        h_prime = 2 * h + b
        x_new = l + (h_prime + 1) // 2
        y_new = l - (h_prime // 2)
        if 0 <= x_new <= 255 and 0 <= y_new <= 255:
            # [C] 執行嵌入
            img[r, c] = x_new
            img[r, c+1] = y_new
        else:
            # 若溢位則不嵌入 (簡單策略：保持原值或僅改 LSB)
            # 為了演示方便，我們這裡不做任何更動
            print(f"   座標 ({r},{c}~{c + 1}): 原值({x}, {y}) -> 擴張後會溢位 (Overflow)，跳過。")

img = img.astype(np.uint8)
cv2.imshow('DE', img)

def get_hide_size(img):
    size = 0
    img_height, img_width = img.shape
    img = img.astype(np.int32)
    for r in range(img_height):
        for c in range(0, img_width, 2):
            x = img[r, c]
            y = img[r, c + 1]
            l = (x + y) // 2
            h = x - y
            b = 1
            h_prime = 2 * h + b
            x_new = l + (h_prime + 1) // 2
            y_new = l - (h_prime // 2)
            if 0 <= x_new <= 255 and 0 <= y_new <= 255:
                # [C] 執行嵌入
                img[r, c] = x_new
                img[r, c + 1] = y_new
            else:
                # 若溢位則不嵌入 (簡單策略：保持原值或僅改 LSB)
                # 為了演示方便，我們這裡不做任何更動
                print(f"   座標 ({r},{c}~{c + 1}): 原值({x}, {y}) -> 擴張後會溢位 (Overflow)，跳過。")

img_stego = img.copy()

print("\n--- 開始提取與還原 ---")

# 1. 準備還原的畫布
img_recovered = np.zeros_like(img_stego)
height, width = img_stego.shape

# 必須先轉型為 int32 以處理負數運算
img_stego_int = img_stego.astype(np.int32)

extracted_bits = []

# 2. 遍歷每一個像素對 (順序必須與嵌入時完全一致)
for r in range(height):
    for c in range(0, width, 2):
        # 讀取含密像素
        x_prime = img_stego_int[r, c]
        y_prime = img_stego_int[r, c + 1]

        # [A] 逆向變換 (計算 l 和 h')
        l = (x_prime + y_prime) // 2
        h_prime = x_prime - y_prime

        # 提取秘密位元 (LSB)
        # h' = 2*h + b，所以 b 就是 h' 除以 2 的餘數
        b_extracted = h_prime % 2
        extracted_bits.append(b_extracted)

        # [C] 還原原始差值 h
        # h = floor(h' / 2)
        h_rec = h_prime // 2

        # 還原原始像素
        x_rec = l + (h_rec + 1) // 2
        y_rec = l - (h_rec // 2)

        # 存入還原圖
        # 注意：這裡需防呆，雖然理論上可逆，但下面會解釋 "位置圖" 的問題
        img_recovered[r, c] = np.clip(x_rec, 0, 255)
        img_recovered[r, c + 1] = np.clip(y_rec, 0, 255)

# 轉回 uint8 顯示
img_recovered = img_recovered.astype(np.uint8)


# 顯示結果
cv2.imshow('Recovered Image', img_recovered)
print("提取完成！(部分數據可能錯誤，請見解釋)")

# 等待按鍵按下 (參數 0 代表無限期等待)
cv2.waitKey(0)

# 關閉所有視窗
cv2.destroyAllWindows()

# 儲存結果
cv2.imwrite('DE.jpg', img)