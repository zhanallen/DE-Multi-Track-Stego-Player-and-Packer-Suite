# 缺陷紀錄 (Defect Log)

嚴重度定義依 `SYSTEM_TEST_PLAN.md` §4.2：Blocker（崩潰/當機）、Critical（可逆性失敗/音軌損毀/畫質低於門檻）、Major（功能異常但不影響核心流程）、Minor。
每筆缺陷的證據必須指向 repo 內可重現的驗證腳本與其 log。

---

## DEF-001　分塊音軌合併後切點插入 31.6 ms 靜音，之後音訊延遲 30.2 ms

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Fixed（待 commit 後於乾淨工作區重驗）** |
| 模組 | MOD-PK / MOD-PL — `src/audio_chunker.py`（`split_audio_into_chunks`、`concatenate_chunks`） |
| 發現日期 | 2026-10-27 |
| 發現版本 | `a5919e0` |
| 測試載體 | `src/test/video/pixel_jimmy/`（來源見 `SOURCES.txt`） |

### 現象
StegoPlayer 擷取出的完整音軌比原始 mp3 多 1,332 個取樣（44.1 kHz）。切點（`initial_sec`）後 +6.2 ms 處出現 31.6 ms 近乎全靜音的缺口，之後整段音訊相對影像延遲 +30.20 ms。14 軌皆同。擷取音軌與原檔的 SHA-256、解碼 PCM 均不相同。

### 根本原因
`split_audio_into_chunks` 以 `libmp3lame -b:a 192k` 將兩段各自重新編碼，`concatenate_chunks` 再以 concat demuxer `-c copy` 串接。單檔播放時解碼器依 LAME/Info 標頭去除頭尾填充，但串接後 chunk0 的尾端填充（227 samples）與 chunk1 的編碼器延遲（1,105 samples）留在接縫：227 + 1,105 = **1,332**，與實測完全一致。另一後果：擷取音軌為有損重新編碼結果，永遠無法與原檔位元級相同。

### 證據（修正前）
- `src/test/video/pixel_jimmy/boundary_log.txt` — `src/test/verify/verify_chunk_boundary.py`：取樣數 +1,332、切點前延遲 0、切點後延遲 +1,332、切點後 31.6 ms 靜音段
- `src/test/video/pixel_jimmy/audio_log.txt` — `verify_audio.py`：14/14 軌 SHA-256 與 PCM 皆不符
- `src/test/video/pixel_jimmy/chunk_log_3s.txt` — `verify_chunks.py`：chunk0 與本機以 libmp3lame 重切結果位元級相同，確認擷取通道本身無損

### 修正
- `.mp3` 改為在原始檔的 MPEG Layer III frame 邊界直接切位元組（不重新編碼），切點為累計音訊 ≥ `initial_sec` + 1 frame 的第一個 frame 邊界，chunk0 + chunk1 位元組 == 原檔。
- `concatenate_chunks`：後續 chunk 以 frame sync 開頭時直接串接位元組；以 ID3 / Info frame 開頭（舊版重新編碼格式）仍走原 ffmpeg concat，維持既有 stego 檔可播放。
- 無法解析的 MP3 退回原 ffmpeg 重新編碼路徑。

### 驗證（修正後）
- `src/test/video/pixel_jimmy/mp3_split_log.txt` — `verify_mp3_split.py`：14 軌 × `initial_sec` 3.0/6.0 皆 PASS（位元組相等、合併 SHA-256 相等、chunk1 frame sync、chunk0 解碼長度 ≥ initial_sec 且 PCM 為原檔前綴）；舊格式 14 軌仍走 ffmpeg 路徑且輸出與修正前相同
- `src/test/video/pixel_jimmy/e2e_log.txt` — `verify_e2e_pack.py`：以修正後程式封裝 → 擷取，14/14 軌 SHA-256 與原檔相同

### 已知限制 / 後續
- `.m4a` / `.aac` 仍走重新編碼路徑，AAC priming（1,024–2,112 samples）預期造成同類問題，尚未驗證。
- chunk0 保留原檔的 Xing/Info 標頭，其總 frame 數描述的是完整檔案，部分播放器可能顯示錯誤的總時長；StegoPlayer 以 EndOfMedia 與 `initial_sec` 邊界切換，不依賴此值，但未做 GUI 實測。
- 既有以舊版封裝的 stego 檔（如雲端「已藏密」3 支）重新擷取時缺陷仍在，需以新版重新封裝。
- 驗證 log 帶有 `src/ has uncommitted changes` 標記；commit 後需重跑以取得可追溯 log。

---

## DEF-002　分塊串流播放無法維持影音同步：chunk0 期間音訊落後、切點暫停 13–14 秒、切換時跳過約 1.95 秒音訊

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Open** |
| 模組 | MOD-PL — `src/player_app.py`（`on_chunk_received`、`sync_check`、`handoff_to_full_track`、`on_media_status_changed`）、`src/pee_stego.py`（`decode_video_multi`、`files_to_chunked_bits` 的兩段式分塊協議） |
| 發現日期 | 2026-10-27 |
| 發現版本 | `a5919e0` + 工作區修改（DEF-001 修正；本缺陷與該修正無關） |
| 測試載體 | `src/test/video/pixel_jimmy/e2e_stego.mp4`（`verify_e2e_pack.py` 以 `initial_sec=3.0` 封裝 14 軌，payload 80,618,232 bits，179 幀） |
| 測試環境 | LAPTOP-BA0FPL1L，Windows 11 Home 26200，Python 3.11.5，PySide6 6.11.1（Qt Multimedia FFmpeg 7.1.3 後端） |

### 現象（`gui_probe/gui_probe_log.txt`，第 2 次執行）
| 時間（自啟動） | 事件 |
| ---: | :--- |
| 18,979 ms | 收到 chunk0，影片位置 0 ms |
| 19,248 ms | 音訊開始播放（+268 ms） |
| 19,466 → 23,389 ms | **主執行緒停滯 3.9 s**（20 ms 取樣計時器未觸發）；期間影片持續播放 |
| 23,480 ms | 影片 4,421 ms、音訊 1,150 ms → **音訊落後影片約 3.3 s** |
| 25,313 ms | chunk0 播完（音訊約 2,926 ms），chunk1 未就緒 → **影片暫停於 4,879 ms** |
| 38,579 ms | chunk1 解出（第 179 幀）→ 暫停共 **13.3 s** |
| 38,659 ms | 切換：新播放器自影片位置 4,879 ms 起播，而 chunk0 實際只播到約 2,926 ms → **約 1.95 s 音訊內容被跳過** |

第 1 次執行（冷啟動）：chunk0 解出時影片已在 3,545 ms，超過切點，**chunk0 完全未被播出**；影片暫停 14.0 s；恢復後音訊相對影片穩定落後約 0.6 s（mean −581 ms，n=261）。

### 初步分析（未經修正驗證）
1. **影片不等待 chunk0**：影片載入完成即播放（推測經 `check_and_resume_playback`，`player_app.py:1631`），與 chunk0 是否就緒無關。
2. **主執行緒停滯**：解碼執行緒期間 GUI 事件迴圈出現 2.9–3.9 s 的停滯；推測為解碼執行緒中持有 GIL 的步驟（zlib 解壓、NumPy 緩衝區操作、檔案寫出）。chunk0 期間 `sync_check` 刻意不重新對齊（`player_app.py:1677` 條件），落後無法自行修正。
3. **兩段式協議的結構限制**：chunk1 包含所有音軌的剩餘全部內容，須解完第 179 幀才可用；實測解碼速度 2–9 FPS（同時有 Qt 播放 HEVC 無損 1080p 與擷取管線兩個解碼器），遠低於 23.98 fps 播放速度，`initial_sec=3.0` 下必然在切點暫停。
4. **切換位置取自影片位置**：`on_media_status_changed`（`player_app.py:1732`）對 `audio_player_next` 以 `max(boundary_ms, video_player.position())` 定位，影片超前時直接跳過中間音訊。

### 重現
```
python src/test/verify/verify_e2e_pack.py src/test/video/pixel_jimmy
python src/test/verify/gui_handoff_probe.py src/test/video/pixel_jimmy/e2e_stego.mp4 src/test/video/pixel_jimmy/gui_probe > src/test/video/pixel_jimmy/gui_probe/gui_probe_log.txt
```
截圖：`gui_probe/00_chunk0_playing.png`、`01_waiting_chunk1.png`、`02_after_handoff_0.5s.png`、`03_after_handoff_3s.png`、`04_final.png`（含廣告畫面，已被 `.gitignore` 排除）。

### 限制
- 以播放器位置/狀態推論，未做人耳聆聽。
- 僅 1 支載體、2 次執行；冷/熱啟動結果差異大，尚未量化變異。
- 截圖 00 的時間標籤顯示 00:00，但實際擷取於主執行緒停滯結束後（影片約 4.4 s），標籤未及時更新。

---

## DEF-003　IP 鎖定策略建立 `DetectionResult` 時拋出 TypeError，語系自動匹配中斷

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Open** |
| 模組 | MOD-PL — `src/i18n_detector.py:357`（IP 鎖定策略 `detect`）、呼叫端 `src/player_app.py:1093`（`on_manifest_received`） |
| 發現日期 | 2026-10-27 |
| 引入版本 | **`a5919e0`**（回歸） |

### 現象
StegoPlayer 解出 Manifest 後：
```
File "src/player_app.py", line 1093, in on_manifest_received
    pre_res = detect_best_locale(
File "src/i18n_detector.py", line 357, in detect
    return DetectionResult(
TypeError: DetectionResult.__init__() got an unexpected keyword argument 'confidence'
```
例外於 Qt slot 中拋出，`on_manifest_received` 其後步驟（`ip_matched_track` 設定、音軌徽章更新、`start_i18n_detection`、側欄預選）全部未執行；播放器退回第一軌（本次為 de-DE）。兩次 GUI 執行皆重現（`gui_probe/gui_probe_log.txt` 開頭）。

### 根本原因
- `d228479` 新增 IP 鎖定策略，以 `DetectionResult(..., confidence=1.0, ...)` 建立結果。
- `a5919e0` 將 `DetectionResult.confidence` 改為由 `CONFIDENCE_WEIGHTS[resolved_by]` 推導的唯讀 property（`i18n_detector.py:87-90`），並新增必填欄位 `resolved_by`（`:82`），但未更新 `:357` 的呼叫：仍傳入 `confidence`、且缺少 `resolved_by`。

### 影響
- IP 鎖定模式下，依地區自動選擇預設音軌的功能完全失效。
- 依 Q4-5 確認的規格（STP 1.2），IP 鎖定為選用功能、預設關閉；但現行程式預設開啟（DEF-005），因此**目前所有使用者一啟動播放器就會走到此路徑**。修正 DEF-005 後，影響範圍縮小為「手動開啟 IP 鎖定的使用者」，但本缺陷仍須修正。

### 重現
在預設 `ip_lock_mode=True` 下以 StegoPlayer 載入任何分塊格式 stego 影片，或執行上述 `gui_handoff_probe.py`。

---

## DEF-004　chunk0 音軌回報的總時長為整首長度（30.17 s 而非約 3 s）

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Minor** |
| 狀態 | **Open** |
| 模組 | MOD-PK / MOD-PL — `src/audio_chunker.py`（DEF-001 修正後的 MP3 位元組切割） |
| 發現日期 | 2026-10-27 |
| 發現版本 | 工作區（DEF-001 修正後） |

### 現象
- ffmpeg 開啟擷取出的 `de-DE_chunk0.mp3` 時回報 `Duration: 00:00:30.17` 並警告 `filesize and duration do not match (growing file?)`（`gui_probe/gui_probe_log.txt`）。
- Qt `QMediaPlayer.duration()` 對 chunk0 回報 **30,171 ms**；第 1 次執行中 chunk0 播放器位置直接跳至 30,171 ms（`audio_dur` 欄）。

### 根本原因
chunk0 為原檔位元組前綴，保留了原檔的 Xing/Info 標頭；該標頭記錄的總 frame 數屬於完整檔案。此為 DEF-001 修正的已知副作用（見 DEF-001「已知限制」第 2 點）。

### 影響
- StegoPlayer 切換邏輯以 `initial_sec` 邊界與 EndOfMedia 判斷，不直接依賴 chunk0 時長；但 chunk0 播放器的 `duration()`/`position()` 數值不可信，與 DEF-002 的切換判斷交互作用尚未釐清。
- 其他播放器若單獨播放 chunk0，進度列與總時長顯示錯誤。

### 限制
是否造成 DEF-002 中 chunk0 位置跳至 30,171 ms 的直接原因，尚未以修正後重測確認。

---

## DEF-005　IP 鎖定模式預設為開啟，與規格「選用功能、預設關閉」不符

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Open** |
| 模組 | MOD-PL — `src/player_app.py:154`（`QSettings("GradProject", "StegoPlayer").value("ip_lock_enabled", True)`） |
| 發現日期 | 2026-10-27 |
| 依據規格 | `SYSTEM_TEST_PLAN.md` 1.2（Q4-5，2026-10-27 確認） |

### 現象
首次啟動（QSettings 尚無 `ip_lock_enabled` 值）時，`ip_lock_enabled` 預設為 `True`，`detect_best_locale(..., ip_lock_mode=True)`（`player_app.py:1096`、`:1261`）只執行 `IpLockStrategy` 與兜底兩層，**完全略過**使用者歷史偏好、系統語言、時區等五層規格邏輯。

### 規格要求
語系判定採六層決策邏輯（歷史偏好 → 系統語言精確 → 時區消歧 → 系統語言模糊 → GeoIP → 兜底）；IP 鎖定為使用者手動開啟的選用功能，**預設關閉**。

### 影響
- 新安裝的使用者預設走 IP 鎖定路徑，與規格的語系選擇結果不同；且該路徑目前因 DEF-003 拋出例外。
- 已啟動過的機器，QSettings 中可能已保存 `true`；修正預設值後，**既有設定不會自動變更**，修正時須決定是否遷移既有值（待開發端決定）。

### 重現
1. 清除 `HKEY_CURRENT_USER\Software\GradProject\StegoPlayer` 下的 `ip_lock_enabled`（或在新帳號上執行）。
2. 啟動 StegoPlayer 並載入任一分塊格式 stego 影片。
3. 觀察 log：出現 `IP_LOCK` 路徑或 DEF-003 的 TypeError，而非六層邏輯的 `resolved_by`。

### 限制
本缺陷由程式碼審查與規格確認得出，未單獨執行清除設定後的實測；DEF-003 的兩次 GUI 執行可佐證預設確實走 IP 鎖定路徑。
