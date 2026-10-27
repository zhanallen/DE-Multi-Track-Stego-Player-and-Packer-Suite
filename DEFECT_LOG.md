# 缺陷紀錄 (Defect Log)

嚴重度定義依 `SYSTEM_TEST_PLAN.md` §4.2：Blocker（崩潰/當機）、Critical（可逆性失敗/音軌損毀/畫質低於門檻）、Major（功能異常但不影響核心流程）、Minor。
每筆缺陷的證據必須指向 repo 內可重現的驗證腳本與其 log。

---

## DEF-001　分塊音軌合併後切點插入 31.6 ms 靜音，之後音訊延遲 30.2 ms

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Fixed**（修正於 `4016071`；以該 commit 重跑 `mp3_split_log.txt`、`e2e_log.txt` 皆 PASS，標頭乾淨） |
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
- **後續修正（2026-10-27，未 commit）**：`verify_packer_edges.py`（TC-PK-05）發現 MPEG-2 Layer III（576 samples/frame）的 chunk0 解碼後比 `initial_sec` 短約 24 ms（131,422 < 132,300 samples），因原本只多留 1 frame，不足以涵蓋 LAME 編碼器延遲 1,105 samples。`mp3_split_offset` 的餘量改為固定 1,152 samples：MPEG-1 切點不變（`mp3_split_log.txt` 重跑後內容相同），MPEG-2 改為 2 frames（修正後 132,574 samples）。
- `.m4a` / `.aac` 仍走重新編碼路徑，AAC priming（1,024–2,112 samples）預期造成同類問題，尚未驗證。
- chunk0 保留原檔的 Xing/Info 標頭，其總 frame 數描述的是完整檔案，部分播放器可能顯示錯誤的總時長；StegoPlayer 以 EndOfMedia 與 `initial_sec` 邊界切換，不依賴此值，但未做 GUI 實測。
- 既有以舊版封裝的 stego 檔（如雲端「已藏密」3 支）重新擷取時缺陷仍在，需以新版重新封裝。
- 修正前證據（`boundary_log.txt`、`audio_log.txt`、`chunk_log_3s.txt`）比對的是舊版 `chunked_stego.mp4`，以 `4016071` 重跑後仍重現 +1,332 samples，作為修正前狀態的紀錄。

---

## DEF-002　分塊串流播放無法維持影音同步：chunk0 出聲延遲、音訊落後、切點長時間暫停、切換時跳過音訊

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major**（發布前必修，SYSTEM_TEST_PLAN 4.2／Q6b） |
| 狀態 | **Open** |
| 模組 | MOD-PL — `src/player_app.py`（`on_chunk_received`、`sync_check`、`handoff_to_full_track`、`on_media_status_changed`）、`src/pee_stego.py`（`decode_video_multi`、`files_to_chunked_bits` 的兩段式分塊協議） |
| 發現日期 | 2026-10-27 |
| 發現版本 | `a5919e0` + 工作區修改；**以 `4016071` 重現** |
| 測試載體 | `src/test/video/pixel_jimmy/e2e_stego.mp4`（`verify_e2e_pack.py` 以 `initial_sec=3.0` 封裝 14 軌，payload 80,618,232 bits，179 幀） |
| 測試環境 | LAPTOP-BA0FPL1L，Windows 11 Home 26200，Python 3.11.5，PySide6 6.11.1（Qt Multimedia FFmpeg 7.1.3 後端） |

### 現象（`gui_probe/gui_probe_log.txt`，commit `4016071`，標頭乾淨）
| 時間（自探針啟動） | 事件 |
| ---: | :--- |
| 11,877 ms | 開始載入 stego 影片 |
| 32,706 ms | 收到 chunk0（載入後 **20.8 s**），影片位置 0 ms |
| 33,131 ms | 音訊播放器進入 Playing 狀態（+416 ms），但位置停在 0 |
| 33,185 → 39,675 ms | **主執行緒停滯 6.5 s**（20 ms 取樣計時器未觸發） |
| 39,675 → 42,093 ms | 影片位置跳到 3,545 ms 後停住，狀態仍為 Playing |
| 42,389 ms | 影片 4,045 ms、音訊 0 ms → **音訊落後影片約 4.0 s** |
| 42,651 ms | 音訊位置才開始前進（收到 chunk0 後 **9.9 s**） |
| 45,584 ms | chunk0 播到約 2,979 ms，chunk1 未就緒 → **影片暫停於 4,045 ms** |
| 45,606 → 51,593 ms | 主執行緒再次停滯 6.0 s |
| 61,937 ms | chunk1 解出（第 179 幀；載入後 50.1 s，平均約 3.6 FPS）→ 暫停共 **16.3 s** |
| 61,964 ms | 切換：新播放器自影片位置 4,045 ms 起播，而 chunk0 只播到約 2,979 ms → **約 1.07 s 音訊內容被跳過** |

**先前執行（commit 前，log 已被覆蓋，不可追溯，僅供參考）**：另兩次執行分別觀察到「chunk0 解出時影片已超過切點、chunk0 完全未播出，暫停 14.0 s」與「主執行緒停滯 3.9 s、音訊落後 3.3 s、暫停 13.3 s、切換跳過約 1.95 s」。三次結果的數值差異大，但現象一致。

**機器狀態較快時（`py310/gui_probe/gui_probe_log.txt`，commit `2bedda9`，Python 3.10.11）**：載入後 2.5 s 收到 chunk0、6.4 s 收到 chunk1（約 28 FPS），**影片未暫停**，最長停滯 0.45 s。但缺陷仍在、程度較輕：
- 收到 chunk0 後 1.5 s 音訊位置才開始前進，chunk0 期間影片最多領先音訊 1.41 s；
- 切換時舊播放器在 2,352 ms、新播放器從影片位置 3,003 ms 起播 → **約 0.65 s 音訊被跳過**；
- 切換後音訊－影片差平均 +272 ms（n=278，min −92、max +332）。

同一 commit 下腳本環境的擷取耗時在 4.7～27.4 s 之間變動（SYSTEM_TEST_PLAN 3.2.2），因此 DEF-002 的嚴重程度隨機器負載變化；修正後的驗收須同時在快、慢兩種狀態下通過。

### 初步分析（未經修正驗證）
1. **影片不等待 chunk0**：影片載入完成即播放（推測經 `check_and_resume_playback`，`player_app.py:1631`），與 chunk0 是否就緒無關。
2. **主執行緒停滯**：解碼執行緒期間 GUI 事件迴圈出現最長 6.5 s 的停滯；推測為解碼執行緒中持有 GIL 的步驟（zlib 解壓、NumPy 緩衝區操作、檔案寫出）。chunk0 期間 `sync_check` 刻意不重新對齊（`player_app.py:1677` 條件），落後無法自行修正。
3. **兩段式協議的結構限制**：chunk1 包含所有音軌的剩餘全部內容，須解完第 179 幀才可用；GUI 內實測擷取平均約 3.6 FPS、瞬時 1–3 FPS（同時有 Qt 播放 HEVC 無損 1080p 與擷取管線兩個解碼器；腳本環境約 6.5 FPS，`e2e_log.txt`），遠低於 23.98 fps 播放速度，`initial_sec=3.0` 下必然在切點暫停。
4. **切換位置取自影片位置**：`on_media_status_changed`（`player_app.py:1732`）對 `audio_player_next` 以 `max(boundary_ms, video_player.position())` 定位，影片超前時直接跳過中間音訊。

### 重現
```
python src/test/verify/verify_e2e_pack.py src/test/video/pixel_jimmy
python src/test/verify/gui_handoff_probe.py src/test/video/pixel_jimmy/e2e_stego.mp4 src/test/video/pixel_jimmy/gui_probe > src/test/video/pixel_jimmy/gui_probe/gui_probe_log.txt
```
截圖：`gui_probe/00_chunk0_playing.png`、`01_waiting_chunk1.png`、`02_after_handoff_0.5s.png`、`03_after_handoff_3s.png`、`04_final.png`（含廣告畫面，已被 `.gitignore` 排除）。

### 限制
- 以播放器位置/狀態推論，未做人耳聆聽。
- 僅 1 支載體；三次執行數值差異大，尚未量化變異。
- 截圖擷取時間受主執行緒停滯影響，可能晚於排定時間；畫面上的時間標籤也可能未及時更新。

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
在預設 `ip_lock_mode=True` 下以 StegoPlayer 載入任何分塊格式 stego 影片，或執行上述 `gui_handoff_probe.py`。Python 3.10.11 下同樣重現（`py310/gui_probe/gui_probe_log.txt`）。

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

---

## DEF-006　payload 跨越容量為 0 的幀（如全黑幀）時，封裝顯示成功但擷取失敗，整段音軌無法取回

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Critical**（payload 損毀，SYSTEM_TEST_PLAN 4.3） |
| 狀態 | **Open** |
| 模組 | MOD-ALG／MOD-PK／MOD-PL — `src/pee_stego.py:511-512`（`coltuc_embed_frame` 略過幀）、`src/pee_stego.py:781`（`decode_video_multi` 對每幀呼叫 `coltuc_decode_frame`） |
| 發現日期 | 2026-10-27 |
| 引入版本 | `f085fb2`（2026-06-30，Coltuc 引擎導入）；於 `c834aa9` 重現 |
| 證據 | `src/test/video/synthetic/zero_cap_log.txt` — `src/test/verify/verify_zero_capacity_frames.py` |

### 現象
載體為 shapes ×2 → **black ×2** → shapes ×22（1920×1080，合成影片，可由 `gen_synthetic.py` 重現），封裝一軌 mp3（724,887 bytes）：
- `encode_video_multi` 回報「🎉 多檔案編碼寫入無損影片成功！」，沒有任何警告。
- `decode_video_multi` 在第一個黑幀拋出 `zlib.error: Error -5 while decompressing data: incomplete or truncated stream`，轉為 `ValueError: 💥 致命失敗…影片可能無嵌入資訊或已被壓縮失真！`。
- 單體格式與分塊格式皆失敗；分塊格式下 Manifest 與 Chunk0 已在前 2 幀解出，Chunk1 永遠無法取得。

### 根本原因
- 封裝端：`coltuc_embed_frame` 在 `capacity <= nresv + 16`（容量連標頭都放不下）時直接 `return gpos, False`，**不寫入任何標頭**，該幀保持原樣，payload 移到下一幀繼續。
- 擷取端：`decode_video_multi` 沒有「本幀是否有嵌入」的判定，在擷取完成前對每一幀都呼叫 `coltuc_decode_frame`，把原始像素的 LSB 當成標頭解析，得到垃圾的 `clen`／`nblocks`，zlib 解壓失敗。
- 封裝端與擷取端對「略過的幀」沒有共同的約定。

### 影響
- 任何在 payload 範圍內含有全黑、全白或接近飽和（像素多落在 [2,253] 之外）幀的影片——例如淡入淡出、轉場黑場、片頭片尾——都會在封裝時看似成功、播放時無法取回音軌。StegoPlayer 只能走降級播放。
- 封裝端不會發現，使用者要到播放時才知道。

### 重現
```
python src/test/verify/gen_synthetic.py src/test/video/synthetic
python src/test/verify/verify_zero_capacity_frames.py src/test/video/synthetic src/test/video/pixel_jimmy/audio_de-DE.mp3 src/test/video/synthetic/zero_cap > src/test/video/synthetic/zero_cap_log.txt
```

### 限制
- 只以黑幀實際跑完封裝→擷取。另由負載掃描得知，**高雜訊畫面同樣是零容量**：合成 noise 圖樣（均勻隨機 Y）24 幀全部被 Coltuc 略過、容量 0（`src/test/video/synthetic/load_sweep/noise_log.txt`），white 亦為 0；因此雜訊重的畫面（例如顆粒、低光噪點）出現在 payload 範圍內時，預期也會觸發本缺陷，尚未以封裝→擷取實測。
- 真實影片中觸發的頻率未量化；Pixel 廣告的前 179 幀未觸發（`verify_log.txt` 179/179 幀皆有嵌入），Xiph 載體尚未測試。

---

## DEF-007　容量不足時 StegoPacker 的錯誤處理引用未定義變數 `reply`（NameError）

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Minor** |
| 狀態 | **Open** |
| 模組 | MOD-PK — `src/embed_app.py:415-421` |
| 引入版本 | `8b3e64d`（2026-06-16）或 `135d0af`（2026-08-07）（`git log -L` 顯示兩者皆改過此段） |
| 證據 | 程式碼審查（未執行 GUI） |

### 現象與原因
```python
if self.total_payload_size > self.estimated_capacity:
    QMessageBox.critical(self, "Error", f"Audio payload (...) exceeds video carrier capacity (...)!")
    if reply == QMessageBox.No:      # ← reply 從未被賦值
        return
```
`QMessageBox.critical(...)` 的回傳值沒有指定給 `reply`，因此 payload 超過估計容量時，顯示錯誤對話框後必然拋出 `NameError`。由於例外中斷了函式，結果「恰好」也是不封裝；但流程依賴例外，且 PySide6 會把 traceback 印到 console。

### 影響
目前行為對使用者而言等同「阻擋封裝」；但若有人把此處改成可選擇「仍要繼續」，或例外處理方式改變，行為會不可預期。

### 限制
未以 GUI 實際操作觸發；依程式碼語意判定。

---

## DEF-008　容量不足要等全片編碼完才報錯，並在輸出路徑留下無效的 stego 檔

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Minor** |
| 狀態 | **Open** |
| 模組 | MOD-PK — `src/pee_stego.py`（`encode_video_multi` 結尾的 `if bit_idx < total_bits: raise ValueError(...)`） |
| 證據 | `src/test/video/packer/packer_edges_log.txt` — `src/test/verify/verify_packer_edges.py` |

### 現象
以 API 對 24 幀合成影片（實際容量 1,547,856 B）封裝 14 軌（約 10,076,671 B）：
- 全部 24 幀編碼完成後才拋出 `ValueError: 💥 容量嚴重不足！還有 68234536 bits 未寫入。`
- 輸出路徑留下 **4,613,913 bytes 的 stego 檔**，外觀是正常影片，但 payload 不完整，播放時才會失敗。

### 影響
- GUI 會先以 `estimate_capacity()` 攔截；實測估計值都**低估**（−0.1% ～ −14.4%，見同一 log 的 PK-04a），因此 GUI 路徑目前偏安全。
- 直接呼叫 API、或估計值高估時（例如影片頭尾有大量零容量幀，而估計只取中段 15 幀），使用者會得到一個看似成功的無效檔。

### 建議驗收
容量不足應在寫入前判定（或失敗時刪除輸出檔），且不留下可播放的殘缺檔。

---

## DEF-009　擷取在 chunk0 之後才失敗時，Player 停止播放、無法完成降級

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Open** |
| 模組 | MOD-PL — `src/player_app.py`（`on_extraction_error` 與分塊播放狀態） |
| 證據 | `src/test/video/player_fallback/zero_cap_clean/gui_probe_log.txt`、對照組 `src/test/video/player_fallback/h264_lossy/gui_probe_log.txt` — `src/test/verify/gui_handoff_probe.py` |

### 現象
載入 DEF-006 產生的分塊 stego（Manifest 與 Chunk0 可解出、之後遇到零容量幀失敗），且同資料夾沒有外部音軌：
- 8,655 ms 收到 chunk0 並開始播放；8,657 ms 擷取失敗，log 顯示「進行降級 (Fallback) 處理…」與「切換為『原生載體音訊播放模式』」。
- 之後**影片停在 1,041 ms（Pause）、chunk0 播放器停在 Pause**，到探針結束（約 19 s）都沒有恢復。

對照組：把 stego 有損轉碼為 H.264（標頭在第 0 幀就損毀）時，降級正常，影片完整播到 10,010 ms。

### 初步分析（未經修正驗證）
降級流程在「一開始就失敗」時正常，但在「已進入 chunk0 播放後才失敗」時，未重設 `is_playing_chunk0`／`is_buffering_chunk1` 等狀態、也未恢復影片播放。

### 限制
- 兩支探針的截圖未成功擷取到畫面（全黑），只能以播放器狀態時間線為證。
- 載體原音是否真的出聲，探針無法量測，需人耳確認。
- 早先一次執行時 stego 與原始 mp3 位於同一資料夾，Player 的「本地外部音軌搜尋」直接找到並播放該 mp3，不屬本缺陷情境，該次結果已捨棄。

---

## DEF-010　非英文 Windows 上時區無法判定國家，第 3 層時區消歧與 GeoIP 的 VPN 交叉檢查失效

| 欄位 | 內容 |
| :--- | :--- |
| 嚴重度 | **Major** |
| 狀態 | **Open** |
| 模組 | MOD-PL — `src/i18n_detector.py:106-147`（`get_local_country_by_timezone`）；影響 `TimezoneDisambiguationStrategy`（第 3 層）與 `GeoIpStrategy._is_geoip_reliable`（第 5 層） |
| 證據 | `src/test/video/env/i18n_layers_log.txt` — `src/test/verify/verify_i18n_layers.py` |

### 現象
繁體中文 Windows 11（本測試機，UTC+8）：
```
datetime tzname='台北標準時間'  time.tzname=('台北標準時間', '台北日光節約時間')
get_local_country_by_timezone(['zh-TW']) = None
get_local_country_by_timezone(['en-US']) = None
```

### 根本原因
函式以英文關鍵字（`taipei`、`tst`、`tokyo`、`cst`…）比對 `tzname`；Windows 的 `tzname` 會依顯示語言在地化（例如「台北標準時間」），因此在非英文 Windows 上一律回傳 `None`。

### 影響（依 STP 1.2 六層規格）
- **第 3 層**：時區國碼為 `None` 時，只能用系統語言的主語言碼對照（`zh→TW`、`ja→JP`…）推測國家，等於沒有使用時區訊號。例如系統語言為無區域的 `zh`、實際在中國的使用者會被判為 `zh-TW`。
- **第 5 層**：`_is_geoip_reliable` 在 `tz_country` 為 `None` 時直接回傳 `True`，**VPN 交叉檢查在非英文 Windows 上完全失效**。
- 交接規格與 Q4-5 確認的「時區」訊號，在本專案主要目標使用者（繁中 Windows）上不起作用。

### 限制
- 只在繁中 Windows 實測；其他語系 Windows 依程式碼推論同樣失效。
- 六層邏輯本身（以注入的時區國碼測試）全部通過，見同一 log 的 `[L]` 區段。
