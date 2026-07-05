import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import os
import subprocess
import sys

# 用來獲取 FFMPEG 執行檔的路徑
try:
    import imageio_ffmpeg
except ImportError:
    print("錯誤: 找不到 imageio_ffmpeg。請執行 'pip install imageio-ffmpeg'")
    exit()

# 為了讀取原始 FPS，我們還是稍微用一下 MoviePy 2.0 的功能 (只讀資訊，不處理影像)
try:
    from moviepy import VideoFileClip
except ImportError:
    try:
        from moviepy.editor import VideoFileClip
    except ImportError:
        pass


def main():
    root = tk.Tk()
    root.withdraw()

    print("--- 高效能轉檔程式啟動 ---")

    # 1. 選取影片
    video_path = filedialog.askopenfilename(
        title="請選取原始影片檔案",
        filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv *.flv"), ("All files", "*.*")]
    )

    if not video_path:
        print("使用者取消選取影片。")
        return

    # 2. 讀取原始 FPS (僅讀取 Metadata，速度快)
    original_fps = 0.0
    try:
        clip = VideoFileClip(video_path)
        original_fps = clip.fps
        clip.close()  # 讀完馬上關閉，釋放資源
        print(f"檔案: {os.path.basename(video_path)}")
        print(f"原始 FPS: {original_fps}")
    except Exception as e:
        messagebox.showerror("讀取錯誤", f"無法讀取影片資訊：\n{e}")
        return

    # 3. 輸入目標幀率
    target_fps = 0.0
    while True:
        user_input = simpledialog.askfloat(
            "輸入幀率",
            f"原始 FPS: {original_fps}\n請輸入目標 FPS (建議輸入整數，如 30, 24):",
            minvalue=0.1
        )

        if user_input is None:
            print("使用者取消。")
            return

        if user_input < original_fps:
            target_fps = user_input
            break
        else:
            messagebox.showwarning("錯誤", f"輸入數值 ({user_input}) 必須小於原始 FPS ({original_fps})")

    # 4. 選擇存檔位置
    filename, ext = os.path.splitext(os.path.basename(video_path))
    default_save_name = f"{filename}_fps{int(target_fps)}{ext}"

    save_path = filedialog.asksaveasfilename(
        title="請選擇儲存位置",
        initialfile=default_save_name,
        defaultextension=".mp4",
        filetypes=[("MP4 Video", "*.mp4")]
    )

    if not save_path:
        print("使用者取消存檔。")
        return

    # 5. 建構 FFMPEG 指令 (優化核心)
    # 獲取電腦中的 FFMPEG 執行檔路徑
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    print(f"\n準備開始轉檔... (使用 FFMPEG 直接加速)")
    print(f"目標 FPS: {target_fps}")

    # 指令解釋：
    # -i input : 輸入檔
    # -r target_fps : 設定輸出幀率 (最關鍵的參數)
    # -c:v libx264 : 使用 x264 編碼器 (相容性最好)
    # -preset ultrafast : 極速模式 (優化重點！犧牲微小壓縮率換取巨大速度提升)
    # -c:a copy : 聲音直接複製 (優化重點！完全不重新編碼聲音)
    # -y : 若檔案存在則直接覆蓋
    cmd = [
        ffmpeg_exe,
        '-i', video_path,
        '-r', str(target_fps),
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-c:a', 'copy',
        '-y',
        save_path
    ]

    # 在 Windows 上執行時，隱藏黑視窗 (Optional，如果想看進度可以把這段拿掉)
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        print("正在執行 FFMPEG 指令...")
        # 呼叫 subprocess 執行
        subprocess.run(cmd, check=True, startupinfo=startupinfo)

        messagebox.showinfo("成功", f"極速轉檔完成！\n儲存於: {save_path}")
        print("轉檔成功。")

    except subprocess.CalledProcessError as e:
        messagebox.showerror("轉檔失敗", f"FFMPEG 執行錯誤 (代碼 {e.returncode})")
    except Exception as e:
        messagebox.showerror("錯誤", f"發生未預期的錯誤:\n{e}")


if __name__ == "__main__":
    main()