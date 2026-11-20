# 手動測試檢核表 (Manual Test Checklist)

對應 `TEST_CASES_SPECIFICATION.md` v2.0 中無法自動化、或需要人耳／人眼判斷的案例。
每一項執行後，在「紀錄」欄填寫：執行者、日期、commit（`git rev-parse --short HEAD`）、結果（✅／❌）、備註。
❌ 時請在 `DEFECT_LOG.md` 新增或更新缺陷，並附上螢幕錄影或截圖的位置。

**共通準備**
- 從 repo 根目錄執行，Python 3.11.5，依 `requirements.txt` 安裝。
- 測試素材：`src/test/video/pixel_jimmy/`（依 `SOURCES.txt` 取得）。若沒有 `e2e_stego.mp4`，先執行：
  ```
  python src/test/verify/verify_e2e_pack.py src/test/video/pixel_jimmy
  ```
- 耳機或喇叭音量調到能清楚聽見對白。
- 建議全程螢幕錄影（Win + Alt + R），檔案存在 `src/test/video/manual/`（已被 `.gitignore` 排除）。

---

## M-01　分塊播放聆聽（DEF-002 人耳確認，TC-PLY-005、006、008、TC-PRF-007、010）

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | `python src/player_app.py src/test/video/pixel_jimmy/e2e_stego.mp4` | 從按下播放到**第一次聽到聲音**大約幾秒 | |
| 2 | 看著人物嘴型聽前 3 秒 | 聲音是否和嘴型對得上；若不同步，大約差多少 | |
| 3 | 注意 3 秒切點附近 | 有無**斷音、重複、跳字**；畫面是否停住（「平滑緩衝中」） | |
| 4 | 若畫面停住，記錄停了幾秒，恢復後再聽 5 秒 | 恢復後聲音是否接續停住前的內容，或跳過一段 | |
| 5 | 關閉播放器，再開一次重複 1–4（熱啟動） | 與第一次比較 | |

**通過條件**：開播後 1 秒內出聲、全程音畫同步（主觀無法察覺偏差）、切點無斷音或跳字、影片不暫停。

## M-02　播放中途失敗的降級（DEF-009 人耳確認，TC-PLY-014、TC-REL-003）

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | 把 `src/test/video/synthetic/zero_cap/zero_cap_stego.mp4` 複製到一個**空資料夾**（同資料夾不可有 mp3） | — | |
| 2 | 用 Player 開啟該檔 | 是否出現錯誤或降級訊息 | |
| 3 | 觀察 20 秒 | 影片是否持續播放；是否聽到載體原音 | |
| 4 | 對照組：開啟 `src/test/video/player_fallback/media_h264/e2e_stego_h264_crf23_10s.mp4` | 同上 | |

**通過條件**：兩者都持續播放影片並出現載體原音，不卡住、不崩潰。

## M-03　手動切軌與 Seek（TC-PLY-009、010、012）

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | 開啟 `e2e_stego.mp4`，等到右下角顯示「解碼完成」 | — | |
| 2 | 播放中依序切換到 ja → fr-FR → de-DE | 每次切換後幾秒內出聲；語言是否正確；是否與畫面同步 | |
| 3 | 拖曳進度列到 10 秒 | Seek 後聲音與畫面是否同步 | |
| 4 | 拖曳到 25 秒，再拖回 2 秒（chunk0 範圍內） | 同上；是否卡住 | |
| 5 | 暫停 5 秒後繼續 | 恢復後是否同步 | |

**通過條件**：切軌後 1 秒內出聲且為正確語言；所有 Seek 與暫停後音畫同步。

## M-04　容量不足的 GUI 行為（DEF-007，TC-PCK-005、006）

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | 以 console 啟動：`python src/embed_app.py` | — | |
| 2 | 載體選 `src/test/video/synthetic/synthetic_shapes_1920x1080_24f.y4m`（容量約 1.5 MB） | 顯示的估計容量 | |
| 3 | 加入 `pixel_jimmy/` 的 14 支 mp3（約 10 MB），按下封裝 | 是否出現「exceeds capacity」對話框 | |
| 4 | 按下對話框的確定 | console 是否出現 `NameError: name 'reply' is not defined`；程式是否仍可操作；是否產生輸出檔 | |

**通過條件**：顯示錯誤對話框、console 無例外、不產生輸出檔、程式可繼續操作。

## M-05　一般播放器相容（TC-SEC-002）

前置：已從 Microsoft Store 安裝「HEVC 視訊擴充功能」。

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | 在檔案總管對 `e2e_stego.mp4` 按右鍵 → 開啟方式 → 媒體播放器 | 能否開啟、畫面是否正常（無花屏、色偏） | |
| 2 | 播放 10 秒 | 是否聽到載體原音 | |
| 3 | 拖曳到 20 秒、再拖回 0 秒 | 是否順暢、無錯誤 | |

**通過條件**：正常播放與拖曳，無花屏、無錯誤訊息。

## M-06　外部 FFmpeg 回歸（範圍外觀察，K-1 後非必要）

前置：另行安裝一個系統 FFmpeg（版本記錄於紀錄欄），取得其 `ffmpeg.exe` 完整路徑。

```
set IMAGEIO_FFMPEG_EXE=C:\path\to\ffmpeg.exe
python src/test/verify/verify_ffmpeg_source.py src/test/video/pixel_jimmy/audio_de-DE.mp3
python src/test/verify/verify_e2e_pack.py src/test/video/pixel_jimmy
python src/test/verify/verify_jimmy.py src/test/video/pixel_jimmy
```

**通過條件**：`verify_e2e_pack` 為 `[RESULT] PASS`；`verify_jimmy` 的 `restore_fail_frames=0`、max|Δ| = 1。log 標頭的 ffmpeg 欄位為系統版本。

## M-07　打包與乾淨環境（TC-POR-001、TC-AVL-001）

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | 建立 `.venv` 並安裝 `requirements.txt`，執行 `build.bat` | 3 個 exe 是否產生於 `dist/`、有無錯誤 | |
| 2 | 在**乾淨的 Win11 VM**（無 Python、無 FFmpeg、無 Node.js）複製 `dist/` | — | |
| 3 | 依序啟動 MultiAudioDownloader、StegoPacker、StegoPlayer | 是否啟動；有無缺 DLL 對話框 | |
| 4 | 在 VM 內用 StegoPacker 封裝 2 支 mp3 到一支短影片，再用 StegoPlayer 播放 | 封裝成功、可播放、可切軌 | |
| 5 | 在 VM 內啟動 MultiAudioDownloader 並輸入任一 URL | 無 Node.js 時是否出現友善提示、不崩潰（TC-DL-03） | |

**通過條件**：3 個 exe 在乾淨 VM 上都能啟動並完成步驟 4；步驟 5 不崩潰。

## M-08　下載器 GUI（SRS 範圍外，K-1 後非必要）

後端流程已由 `verify_downloader.py` 自動化（測試 URL：https://www.youtube.com/watch?v=xzyhqtLrEd4，已獲同意）。本項只確認 GUI 顯示與操作；目前受 DEF-011 影響，需先更新 yt-dlp 才會列出配音語系。

| 步驟 | 操作 | 觀察重點 | 紀錄 |
| :---: | :--- | :--- | :--- |
| 1 | `python src/download_app.py`，貼上上述 URL | 是否列出全部語系音軌 | |
| 2 | 勾選 3 種語系下載 | 檔名是否為 `*_audio_<lang>.mp3`；是否可播放 | |
