import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os

import stego


class StegoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("影片藏密小工具")
        # 為了容納新設定，稍微拉高了視窗
        self.root.geometry("520x550")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 10))
        style.configure("TButton", font=("Arial", 10))
        style.configure("TLabelframe.Label", font=("Arial", 11, "bold"))

        self.create_widgets()

    def create_widgets(self):
        # ==================== 進階設定區塊 ====================
        adv_frame = ttk.LabelFrame(self.root, text="⚙️ 進階設定 (抗壓縮參數)", padding=(15, 10))
        adv_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(adv_frame, text="強度 (Delta):").grid(row=0, column=0, sticky="w", pady=5)
        self.delta_var = tk.IntVar(value=20)  # 預設提高到 20 對抗 LINE
        ttk.Spinbox(adv_frame, from_=5, to=50, textvariable=self.delta_var, width=5).grid(row=0, column=1, padx=5)
        ttk.Label(adv_frame, text="(越大越抗壓縮，但畫面雜訊越明顯)").grid(row=0, column=2, sticky="w")

        ttk.Label(adv_frame, text="重複影格數:").grid(row=1, column=0, sticky="w", pady=5)
        self.repeat_var = tk.IntVar(value=5)
        ttk.Spinbox(adv_frame, from_=1, to=30, textvariable=self.repeat_var, width=5).grid(row=1, column=1, padx=5)
        ttk.Label(adv_frame, text="(加密/解密需一致。越大越抗掉幀)").grid(row=1, column=2, sticky="w")

        # ==================== 加密區塊 ====================
        encode_frame = ttk.LabelFrame(self.root, text="🔒 影片加密 (寫入資料)", padding=(15, 10))
        encode_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(encode_frame, text="1. 選擇載體影片:").grid(row=0, column=0, sticky="w", pady=5)
        self.enc_video_path = tk.StringVar()
        ttk.Entry(encode_frame, textvariable=self.enc_video_path, width=32).grid(row=0, column=1, padx=5)
        ttk.Button(encode_frame, text="瀏覽",
                   command=lambda: self.select_file(self.enc_video_path, [("Video Files", "*.mp4 *.avi")])).grid(row=0,
                                                                                                                 column=2)

        ttk.Label(encode_frame, text="2. 選擇隱藏檔案:").grid(row=1, column=0, sticky="w", pady=5)
        self.enc_data_path = tk.StringVar()
        ttk.Entry(encode_frame, textvariable=self.enc_data_path, width=32).grid(row=1, column=1, padx=5)
        ttk.Button(encode_frame, text="瀏覽",
                   command=lambda: self.select_file(self.enc_data_path, [("All Files", "*.*")])).grid(row=1, column=2)

        ttk.Label(encode_frame, text="3. 儲存影片為:").grid(row=2, column=0, sticky="w", pady=5)
        self.enc_output_path = tk.StringVar()
        ttk.Entry(encode_frame, textvariable=self.enc_output_path, width=32).grid(row=2, column=1, padx=5)
        ttk.Button(encode_frame, text="另存",
                   command=lambda: self.save_file(self.enc_output_path, [("MP4 Video", "*.mp4")], ".mp4")).grid(row=2,
                                                                                                                column=2)

        self.btn_encode = ttk.Button(encode_frame, text="開始加密", command=self.start_encode)
        self.btn_encode.grid(row=3, column=0, columnspan=3, pady=10)

        # ==================== 解密區塊 ====================
        decode_frame = ttk.LabelFrame(self.root, text="🔓 影片解密 (提取資料)", padding=(15, 10))
        decode_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(decode_frame, text="1. 選擇含密影片:").grid(row=0, column=0, sticky="w", pady=5)
        self.dec_video_path = tk.StringVar()
        ttk.Entry(decode_frame, textvariable=self.dec_video_path, width=32).grid(row=0, column=1, padx=5)
        ttk.Button(decode_frame, text="瀏覽",
                   command=lambda: self.select_file(self.dec_video_path, [("Video Files", "*.mp4 *.avi")])).grid(row=0,
                                                                                                                 column=2)

        ttk.Label(decode_frame, text="2. 儲存解密資料:").grid(row=1, column=0, sticky="w", pady=5)
        self.dec_output_path = tk.StringVar()
        ttk.Entry(decode_frame, textvariable=self.dec_output_path, width=32).grid(row=1, column=1, padx=5)
        ttk.Button(decode_frame, text="另存",
                   command=lambda: self.save_file(self.dec_output_path, [("All Files", "*.*")], "")).grid(row=1,
                                                                                                          column=2)

        self.btn_decode = ttk.Button(decode_frame, text="開始解密", command=self.start_decode)
        self.btn_decode.grid(row=2, column=0, columnspan=3, pady=10)

        self.status_var = tk.StringVar()
        self.status_var.set("狀態：等待操作...")
        ttk.Label(self.root, textvariable=self.status_var, foreground="blue").pack(side="bottom", pady=5)

    def select_file(self, string_var, filetypes):
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if filepath: string_var.set(filepath)

    def save_file(self, string_var, filetypes, defaultextension):
        filepath = filedialog.asksaveasfilename(filetypes=filetypes, defaultextension=defaultextension)
        if filepath: string_var.set(filepath)

    def start_encode(self):
        v_path = self.enc_video_path.get()
        d_path = self.enc_data_path.get()
        o_path = self.enc_output_path.get()

        try:
            r_frames = self.repeat_var.get()
            delta_val = self.delta_var.get()
        except tk.TclError:
            messagebox.showerror("錯誤", "進階設定參數必須為整數！")
            return

        if not (v_path and d_path and o_path):
            messagebox.showwarning("警告", "請完整選擇加密所需的檔案路徑！")
            return

        self.btn_encode.config(state="disabled")
        self.status_var.set(f"狀態：加密中 (Delta: {delta_val}, 重複影格: {r_frames})...")
        threading.Thread(target=self._run_encode, args=(v_path, d_path, o_path, r_frames, delta_val),
                         daemon=True).start()

    def _run_encode(self, v_path, d_path, o_path, r_frames, delta_val):
        try:
            stego.robust_encode_h264(v_path, d_path, o_path, r_frames, delta_val)
            self.root.after(0, self._process_complete, "加密完成！")
        except Exception as e:
            self.root.after(0, self._process_failed, f"加密失敗：{str(e)}")
        finally:
            self.root.after(0, lambda: self.btn_encode.config(state="normal"))

    def start_decode(self):
        v_path = self.dec_video_path.get()
        o_path = self.dec_output_path.get()

        try:
            r_frames = self.repeat_var.get()
        except tk.TclError:
            messagebox.showerror("錯誤", "進階設定參數必須為整數！")
            return

        if not (v_path and o_path):
            messagebox.showwarning("警告", "請完整選擇解密所需的檔案路徑！")
            return

        self.btn_decode.config(state="disabled")
        self.status_var.set(f"狀態：解密中 (假設重複影格為: {r_frames})...")
        threading.Thread(target=self._run_decode, args=(v_path, o_path, r_frames), daemon=True).start()

    def _run_decode(self, v_path, o_path, r_frames):
        try:
            stego.robust_decode_h264(v_path, o_path, r_frames)
            self.root.after(0, self._process_complete, "解密成功！檔案已儲存。")
        except Exception as e:
            self.root.after(0, self._process_failed, f"解密失敗：{str(e)}")
        finally:
            self.root.after(0, lambda: self.btn_decode.config(state="normal"))

    def _process_complete(self, msg):
        self.status_var.set("狀態：閒置")
        messagebox.showinfo("成功", msg)

    def _process_failed(self, error_msg):
        self.status_var.set("狀態：發生錯誤")
        messagebox.showerror("錯誤", error_msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = StegoApp(root)
    root.mainloop()