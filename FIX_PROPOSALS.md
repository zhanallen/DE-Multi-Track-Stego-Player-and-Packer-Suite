# 缺陷修正建議書 (Fix Proposals)

| 版本 | 日期 | 對應 | 狀態 |
| :--- | :--- | :--- | :--- |
| v0.1 | 2026-10-27 | `DEFECT_LOG.md` DEF-002～010 | 建議（**未實作、未驗證**）；由開發端評估後決定 |

每項建議都列出：根本原因（已證實／推測）、修正方向、取捨、驗收方式。「推測」項須先以除錯或測試確認後再修。

---

## DEF-006（Critical）payload 跨越零容量幀時擷取失敗

**根本原因（已證實）**：`coltuc_embed_frame`（`pee_stego.py:511`）對容量不足的幀不寫標頭、原樣輸出；`decode_video_multi`（`:781`）沒有「本幀是否有嵌入」的判定，把原始像素 LSB 當標頭解析。

**零容量幀無法存放任何資訊**（連標頭都放不下），所以「略過」這件事必須讓解碼端能自行判斷。

| 方案 | 做法 | 優點 | 缺點 |
| :--- | :--- | :--- | :--- |
| **A（建議）標頭驗證** | 每幀標頭加入固定 magic（例如 4 bytes）與 CRC32（涵蓋 resv_rows、nblocks、clen、n_chunk、cmap）。解碼端驗證失敗即視為「略過幀」：不還原、不取 payload，繼續下一幀 | 改動集中在標頭讀寫；誤判機率約 2⁻⁶⁴；不需預掃 | 標頭增加 64 bits；需版本判斷以相容舊檔（舊標頭無 magic → 走舊解析） |
| B 預掃略過清單 | 封裝前先掃一遍算出各幀容量，把略過幀的索引寫進 Manifest | 解碼端確定性高 | 封裝多一次全片解碼；單體格式沒有 Manifest 要另外處理 |
| C 解碼端重算分類 | 解碼端對當前幀跑 `coltuc_classify` 判斷是否略過 | 不改格式 | **不可行**：嵌入後的幀分類結果會改變，無法可靠重現封裝端的判斷 |

**另外建議**：封裝端統計略過幀數，>0 時在 log／GUI 顯示警告。

**驗收**：
- `verify_zero_capacity_frames.py`：單體與分塊皆 `RESULT PASS`。
- 另構造「雜訊幀」版本（`synthetic_noise`）重跑同一測試。
- 全套回歸：`verify_jimmy.py`、`verify_e2e_pack.py`、`verify_load_sweep.py`（合成組）結果與修正前一致（標頭變長會使容量略減，需接受該差異並記錄）。
- 舊格式 stego（`pixel_jimmy/chunked_stego.mp4`）仍可擷取（`verify_audio.py`）。

---

## DEF-002（Major，必修）分塊串流播放無法維持影音同步

**根本原因（分項）**

| # | 原因 | 狀態 |
| :---: | :--- | :--- |
| 1 | 影片不等 chunk0 就開始播放 | 推測（`check_and_resume_playback`，`player_app.py:1631`） |
| 2 | 切換時新播放器定位到「影片位置」而非「舊音訊位置」，影片超前時跳過音訊 | 已證實（`player_app.py:1732`；探針 log 跳過 0.65～1.07 s） |
| 3 | chunk0 期間 `sync_check` 刻意不重新對齊（`:1677`），落後無法修正 | 已證實（程式碼） |
| 4 | 兩段式協議：chunk1 需解完全部 payload 幀才可用，擷取速度低於播放速度時必然暫停 | 已證實（GUI 擷取 1–28 FPS 隨機器狀態變動） |
| 5 | 擷取期間主執行緒停滯 0.45～6.5 s | 已證實現象；原因推測為擷取執行緒中持 GIL 的步驟 |

**修正方向（建議分兩階段）**

第一階段（小改動，針對 1、2、3）：
- 影片在 chunk0 就緒前保持暫停並顯示緩衝畫面。
- 切換時以舊音訊播放器的位置為準定位新播放器；若與影片差距超過門檻，暫停影片等音訊追上，而不是跳過音訊。
- chunk0 期間也允許溫和對齊（例如差距 > 200 ms 時調整影片而非音訊）。

第二階段（協議／架構，針對 4、5）：
- 分塊協議改為多段（例如每 3～5 秒一段），每段在對應播放時間前即可解出；Manifest 記錄各段邊界。
- 擷取改在獨立行程（multiprocessing）執行，避免與 GUI 共用 GIL。
- 取捨：多段協議會改變 stego 格式，需保留舊格式解碼路徑。

**驗收**（STP 4.2：快、慢兩種機器狀態都要通過）：
- `gui_handoff_probe.py`：收到 chunk0 後音訊在 1 s 內前進；切換時新舊位置差 ≤ 50 ms（⏳ 門檻待定）；全程 \|audio − video\| ≤ ⏳ ms；影片不因等待 chunk 暫停。
- 人耳：`MANUAL_TEST_CHECKLIST.md` M-01。

---

## DEF-009（Major）擷取在 chunk0 之後才失敗時，播放卡住

**根本原因（推測，需除錯確認）**：`on_extraction_error`（`player_app.py:1462-1491`）切換到原生載體音訊模式時：
1. 呼叫 `cleanup_temp_dir()`，刪除了**正在播放中的 chunk0 檔案**；
2. 呼叫 `video_player.play()`，但沒有重設 `is_playing_chunk0`、`is_buffering_chunk1`，也沒有停止 `audio_player`。

`sync_check` 仍認為在播 chunk0，偵測到「chunk0 結束、chunk1 未就緒」便暫停影片等待永遠不會出現的 chunk1。

**修正方向**：降級時先停止並清空 `audio_player`／`audio_player_next` 的來源、重設所有分塊狀態旗標，再刪除暫存檔與恢復影片播放。

**驗收**：`gui_handoff_probe.py` 載入 DEF-006 產生的 stego（空資料夾）：影片持續前進至片尾；人耳 M-02。

---

## 小型修正（可同批處理）

| 缺陷 | 位置 | 修正 | 驗收 |
| :--- | :--- | :--- | :--- |
| DEF-003（SRS 範圍外，K-1 暫緩） | `i18n_detector.py:357` | `DetectionResult(...)` 改傳 `resolved_by=`（並在 `CONFIDENCE_WEIGHTS` 加入對應 key），移除 `confidence=` | `verify_i18n_layers.py` 的 `[IP-LOCK]` 不再拋例外 |
| DEF-005（SRS 範圍外，K-1 暫緩） | `player_app.py:154` | QSettings 預設值改為 `False`；決定是否遷移既有使用者的 `true` | 清除設定後首次啟動為關閉（M-03 附帶檢查） |
| DEF-007 | `embed_app.py:415-421` | 刪除 `if reply == ...` 兩行，對話框後直接 `return` | M-04：console 無例外 |
| DEF-008 | `pee_stego.py`（`encode_video_multi`） | 封裝前以實際容量（或保守估計）判定；失敗時刪除輸出檔 | `verify_packer_edges.py` 的 PK-04b：拋例外且 `output file left behind: False` |
| DEF-010（SRS 範圍外） | `i18n_detector.py:106` | 改用 UTC 偏移量與 IANA／Windows 時區 ID（例如 `tzlocal` 或 `GetDynamicTimeZoneInformation` 的 key name，非在地化名稱）判斷國家 | `verify_i18n_layers.py` 的 `[TZ]` 在繁中 Windows 回傳 `TW` |
| DEF-011（SRS 範圍外，K-1 暫緩） | `requirements.txt` | `yt-dlp==2026.8.19`（已驗證可列 13 種語系並下載；發布超過兩週）；更新後重跑 `verify_downloader.py` 並在 Python 3.10 確認可安裝 | TC-DL-01、02 PASS |
| DEF-012（SRS 範圍外） | `download_app.py`（`DownloadThread.run`） | 記錄取不到的語系，完成時回報失敗清單；全部失敗時發出 `error_signal` | 要求不存在的語系時不回報完全成功 |
| DEF-004 | `audio_chunker.py` | chunk0 寫出時改寫或移除 Xing/Info frame 的總幀數（不影響 chunk0+chunk1 位元組還原需另行處理），或僅在 Player 端不依賴 duration | ffmpeg 讀 chunk0 回報約 3 s |

---

## 建議修正順序
1. **11/04 凍結前**（PEP M2：TBD-01、02、08、11 須關閉）：DEF-006（TBD-11，詹皓宇）、DEF-007（TBD-08，已核准）；TBD-01、02 另行處理
2. DEF-009 → DEF-002 第一階段
3. DEF-008、DEF-010
4. DEF-002 第二階段（協議變更，需更新 STP 與 stego 格式說明）
5. DEF-004
