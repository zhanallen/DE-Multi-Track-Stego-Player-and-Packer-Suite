# 系統測試案例規格書 (Test Cases Specification)
## DE 多音軌可逆影音藏密核心系統

| 版本 | 日期 | 依據 | 狀態 |
| :--- | :--- | :--- | :--- |
| v1.0 | 2026-10-27 | `SYSTEM_TEST_PLAN.md` v2.1（自訂編號） | 已取代 |
| **v2.0** | 2026-10-27 | DE-SRS-001 v1.0 附錄 A、DE-PEP-001 v3.0 §6.2、`SYSTEM_TEST_PLAN.md` v3.0 | 草案 |

**編號規則（PEP 6.2.2）**：`TC-<類別>-<三位數>`，與 SRS 需求一一對應（例：REQ-REL-001 → TC-REL-001）。
**狀態**：✅ 通過　❌ 不通過（附缺陷）　◐ 部分通過或僅有非參考平台數據　⏳ 未執行
**證據規則**：證據路徑相對於 `src/test/video/`；每份 log 開頭記錄腳本、commit 與環境。
**正式驗收環境（SRS C-01、C-02、C-07）**：Windows 10 x64、Intel Core i7-1185G7、16 GB、Python 3.13。目前所有實測在主要測試機（Win11、i7-1260P、Python 3.11.5／3.10.11）完成，因此：
- 功能與可逆性結果與平台無關者標 ✅／❌；
- REQ-PRF-006～010 等與效能有關者，本機數據只作參考，一律標 ◐ 或 ❌（參考），正式判定待參考平台重測。

**通過標準（PEP 6.2.4）**：高優先 100% 通過；中、低優先 ≥ 90%；SRS 附錄 C 嚴重性 H 的 TBD（02、07、08、11）全部關閉。

---

## 1. StegoPacker（PCK）

| TC | 需求 | 優先 | 方法 | 程序 | 狀態與證據 |
| :--- | :--- | :---: | :---: | :--- | :--- |
| TC-PCK-001 | 選擇載體影片 | 高 | T | GUI：Browse 選檔，確認輸出路徑為 `<主檔名>_stego.mp4`；取消對話框狀態不變 | ⏳ |
| TC-PCK-002 | 載體容量預估 | 高 | T | GUI 顯示格式與停用按鈕；API：`estimate_capacity()` 與實際容量比對（`verify_packer_edges.py` PK-04a） | ◐ API 部分：估計值低估 0.1～14.4%（`packer/packer_edges_log.txt`）；GUI ⏳ |
| TC-PCK-003 | 新增隱藏音軌 | 高 | T | GUI：多選加入，重複路徑被忽略 | ⏳ |
| TC-PCK-004 | 清除隱藏音軌清單 | 中 | T | GUI：Clear List 後清單為空、使用率歸零 | ⏳ |
| TC-PCK-005 | 負載使用率顯示 | 高 | T | GUI：≤ 100% 綠字、> 100% 紅色粗體 | ⏳ |
| **TC-PCK-006** | 容量超限阻擋 | 高 | T | 自動：`verify_pck006.py`（offscreen，攔截對話框與封裝執行緒）；GUI 目視：M-04 | ✅ DEF-007 修正後通過（`packer/pck006_log.txt`）；修正前重現 NameError |
| TC-PCK-007 | 封裝輸入驗證 | 高 | T | GUI：依序缺載體／音軌／輸出時的警告文字 | ⏳ |
| TC-PCK-008 | 演算法選擇 | 中 | D | GUI：下拉選單含 coltuc_pee、選取後說明更新；不可用演算法須明示（TBD-02） | ⏳（已觀察到 `hevc_rdh_core` 載入警告，見 TBD-02） |
| TC-PCK-009 | 串流切片模式選項 | 高 | T | API：`encode_video_multi(chunked=True/False)` 分別產生 DE_CHUNK_V1 與 Legacy | ✅ `synthetic/zero_cap_log.txt`（兩種格式皆封裝成功並由解碼端正確辨識）、`pixel_jimmy/e2e_log.txt`（DE_CHUNK_V1） |
| TC-PCK-010 | 背景封裝與進度回報 | 高 | D | GUI：封裝中拖曳視窗、進度文字格式 | ⏳ |
| TC-PCK-011 | 封裝結果通知 | 高 | T | GUI：成功與失敗對話框文字 | ⏳ |
| TC-PCK-012 | 自訂輸出路徑 | 低 | T | GUI：Save As | ⏳ |

## 2. 可逆隱寫演算法（ALG）

| TC | 需求 | 優先 | 方法 | 程序 | 狀態與證據 |
| :--- | :--- | :---: | :---: | :--- | :--- |
| TC-ALG-001 | JPEG4 預測與 2×2 區塊 | 高 | I | 程式碼檢查＋逐區塊反推（`verify_distortion_model.py`） | ✅ `images/distortion_model_log.txt` |
| TC-ALG-002 | 處理帶與 skip-map | 高 | T | 逐區塊檢查：處理帶外區塊未修改 | ✅ 同上（skipped-but-changed = 0，9 樣本） |
| TC-ALG-003 | 擴張／平移與四等分散 | 高 | T | 逐區塊比對 u 分配式與 Σu² = \|d\| | ✅ 同上（6,632,602 區塊 0 不符） |
| TC-ALG-004 | 每幀標頭與旁通道 | 高 | T | SSE 恆等式含保留列；還原後保留列 LSB 相同 | ✅ 同上；`pixel_jimmy/verify_log.txt` |
| **TC-ALG-005** | 低容量幀略過 | 中 | T | `verify_zero_capacity_frames.py`：shapes×2 → black×2 → shapes×22，單體與分塊 | ❌ **DEF-006**（TBD-11）；另見 `SRS_PEP_ALIGNMENT.md` §3 的需求可行性說明 |
| TC-ALG-006 | 提取與 Y 平面還原 | 高 | T | `verify_jimmy.py` | ✅ `pixel_jimmy/verify_log.txt`（179/179） |
| TC-ALG-007 | 容量估算方法 | 中 | A | 檢查實作是否符合描述；估計值 vs 實際 | ◐ 實作符合；估計值低估（`packer/packer_edges_log.txt`） |
| TC-ALG-008 | 藏密影片輸出編碼 | 高 | I | SEI 含 lossless、hvc1、yuv420p | ✅ `pixel_jimmy/verify_log.txt` |
| TC-ALG-009 | 管線化平行處理 | 中 | I | 程式碼檢查佇列長度、nogil、快取目錄 | ⏳ |

## 3. 負載容器與音訊切片（CNT）

| TC | 需求 | 優先 | 方法 | 程序 | 狀態與證據 |
| :--- | :--- | :---: | :---: | :--- | :--- |
| TC-CNT-001 | 負載長度標頭 | 高 | T | 正常檔解出長度；不合法長度時拋出錯誤 | ◐ 正常路徑 ✅（`e2e_log.txt`）；不合法長度路徑 ⏳ |
| TC-CNT-002 | Legacy 單體格式 | 高 | T | 單體模式封裝→擷取，SHA-256 比對 | ◐ 單體封裝已執行但受 DEF-006 載體影響未完成擷取（`synthetic/zero_cap_log.txt`）；需以一般載體重跑 |
| TC-CNT-003 | DE_CHUNK_V1 標頭與 Manifest | 高 | T | 解析 Manifest 欄位 | ✅ `pixel_jimmy/e2e_log.txt`（第 1 幀解出 Manifest，14 軌） |
| TC-CNT-004 | Chunk 區段結構 | 高 | T | Chunk 0／1 依序解出且 is_last 正確 | ✅ 同上（第 18、179 幀） |
| TC-CNT-005 | 串流解碼狀態機 | 高 | T | 回呼次數與順序 | ✅ 同上；`pixel_jimmy/gui_probe/gui_probe_log.txt` |
| TC-CNT-006 | 音訊切片 | 高 | T | `verify_mp3_split.py`（initial_sec 3.0／6.0）；`verify_packer_edges.py` PK-05 | ✅ 位元組切割（DEF-001 修正後）；**與 SRS 現行描述（libmp3lame 重新編碼）不同，SRS v1.1 需改寫** |
| TC-CNT-007 | 音訊片段合併 | 高 | T | 合併檔 SHA-256 與原檔相同；舊格式走 ffmpeg concat | ✅ `pixel_jimmy/mp3_split_log.txt`、`e2e_log.txt`（同上，需改寫 SRS） |
| TC-CNT-008 | 音軌語系 ID 解析 | 中 | T | 各種檔名樣式 | ◐ 間接驗證（14/14 正確）；專門案例 ⏳ |

## 4. StegoPlayer（PLY）

| TC | 需求 | 優先 | 方法 | 程序 | 狀態與證據 |
| :--- | :--- | :---: | :---: | :--- | :--- |
| TC-PLY-001 | 開啟藏密影片 | 高 | T | 命令列參數、首頁按鈕、播放列按鈕；不存在檔案停留首頁 | ◐ API 載入 ✅（探針）；其餘 ⏳ |
| **TC-PLY-002** | 背景串流解碼（GUI 阻塞 ≤ 200 ms） | 高 | T | `gui_handoff_probe.py` 量測 20 ms 取樣間隔中的停滯 | ❌（參考）**DEF-002**：停滯 0.45～6.5 s |
| TC-PLY-003 | 緩衝 HUD | 中 | D | 目視 | ⏳ |
| TC-PLY-004 | 音軌清單呈現 | 高 | T | 收到 Manifest 後側邊欄項目數與名稱 | ⏳ |
| **TC-PLY-005** | 首塊自動開播 | 高 | T | 探針：Chunk 0 後音訊位置開始前進 | ❌ **DEF-002**（收到後 1.5～9.9 s 才前進） |
| **TC-PLY-006** | 無縫接力 | 高 | T | 探針：接力時新舊位置差 | ❌ **DEF-002**（跳過 0.65～1.07 s） |
| TC-PLY-007 | 緩衝不足等待 | 中 | T | 探針：暫停並於 Chunk 1 後恢復 | ✅ 依規格暫停與恢復（`pixel_jimmy/gui_probe/gui_probe_log.txt`） |
| **TC-PLY-008** | 影音同步校正 | 高 | T | 探針：音訊－影片差 > 450 ms 時是否校正 | ❌ **DEF-002**（chunk0 期間不校正，落後最多 4.0 s） |
| TC-PLY-009 | 隱藏音軌熱切換 | 高 | T | M-03 | ⏳ |
| TC-PLY-010 | 開播前待播選擇 | 中 | T | 解碼中點選音軌，確認 Chunk 0 後優先播放 | ⏳ |
| TC-PLY-011 | 載體音訊靜音 | 高 | T | 播放隱藏音軌時 video_audio_output 音量為 0 | ⏳ |
| TC-PLY-012 | 播放控制 | 高 | T | M-03 | ⏳ |
| TC-PLY-013 | 音訊輸出裝置跟隨 | 低 | D | 切換預設輸出裝置 | ⏳ |
| **TC-PLY-014** | 解碼失敗備援 | 高 | T | 探針：有損轉碼 stego、chunk0 後才失敗的 stego（空資料夾） | ◐ 有損轉碼 ✅（`player_fallback/h264_lossy/`）；chunk0 後失敗 ❌ **DEF-009**（`player_fallback/zero_cap_clean/`） |
| TC-PLY-015 | 暫存檔清理 | 高 | T | 開新檔與關閉後 `%TEMP%\temp_extracted_tracks` 為空 | ⏳ |

## 5. 效能（PRF）— 正式判定需在參考平台

| TC | 需求 | 優先 | 程序 | 本機參考數據 | 狀態 |
| :--- | :--- | :---: | :--- | :--- | :---: |
| TC-PRF-001 | PSNR ≥ 55 dB @ 0.20 bpp | 高 | `verify_load_sweep.py` 於 0.20 bpp 的 MSE-first（全片與嵌入幀）；需先定義「平均」算法 | sintel 滿載 0.2234 bpp 時嵌入幀 55.51 dB；Pixel 0.2175 bpp 時 54.96 dB；SVT 無法達到 0.20 bpp（`xiph/load_sweep/summary.md`） | ◐ |
| TC-PRF-002 | SSIM ≥ 0.998 @ 0.20 bpp | 高 | 待在腳本加入 SSIM | — | ⏳ |
| TC-PRF-003 | 像素變動 ≤ 1 | 高 | 同 TC-ALG-002 | 全部樣本 max\|Δ\| = 1 | ✅ |
| TC-PRF-004 | 位元率增量 ≤ 3% @ 0.20 bpp | 中 | `verify_load_sweep.py --encode` | sintel 0.2234 bpp：+35.88%；SVT 滿載（約 0.045 bpp）+1.15～1.50% | ❌ |
| TC-PRF-005 | 容量 ≥ 0.15 bpp（自然 1080p） | 中 | 同上 | SVT 自然場景 0.0436～0.0494 bpp；Pixel（AV1 有損來源）0.2175；sintel（CG）0.2234 | ❌ |
| TC-PRF-006 | 封裝 ≥ 8 fps | 中 | `verify_e2e_pack.py` 多次取中位數 | 3.5～19 fps（隨機器狀態） | ◐ |
| TC-PRF-007 | 首次發聲 ≤ 5 s | 高 | 探針：載入→音訊前進 | 4.0～30.7 s | ❌（參考） |
| TC-PRF-008 | 影音差 ≤ 450 ms | 高 | 探針 | 最多 4.0 s | ❌（參考） |
| TC-PRF-009 | GUI 阻塞 ≤ 200 ms | 中 | 探針 | 0.45～6.5 s | ❌（參考） |
| TC-PRF-010 | 接力無 > 100 ms 靜音或重複 | 中 | 探針＋錄音 | 跳過 0.65～1.07 s | ❌（參考） |

## 6. 品質屬性與其他

| TC | 需求 | 優先 | 方法 | 程序 | 狀態與證據 |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **TC-REL-001** | 載體可逆還原（MD5 一致） | 高 | T | `verify_jimmy.py`；Xiph 載體 `verify_load_sweep.py` 的 restore_fail | ✅ Pixel 179/179；合成控制組全部 0 失敗；Xiph Coltuc 24/24 案例（`xiph/load_sweep/summary.md`） |
| **TC-REL-002** | 負載正確性（BER = 0） | 高 | T | `verify_jimmy.py`、`verify_e2e_pack.py` | ✅ BER = 0；MP3 SHA-256 相同 |
| **TC-REL-003** | 異常輸入容錯 | 高 | T | 同 TC-PLY-014；另含 `drive_bw/`（mp4v 有損）樣本 | ◐（DEF-009） |
| TC-AVL-001 | 離線運作 | 高 | D | 斷網後封裝與播放 | ⏳ |
| TC-SEC-001 | 暫存資料範圍 | 中 | I | 檢查寫入路徑與刪除時機 | ⏳ |
| **TC-SEC-002** | 一般播放器之隱蔽性 | 高 | D | ffprobe 串流數；Windows 媒體播放器（M-05） | ◐ 串流 = 1 HEVC + 1 AAC（`pixel_jimmy/gui_probe/gui_probe_log.txt`）；第三方播放器 ⏳ |
| TC-MNT-001 | 演算法外觀介面 | 中 | I | 檢查 GUI 只經 stego_facade 呼叫 | ⏳ |
| TC-POR-001 | 免安裝執行檔 | 高 | D | 乾淨 VM（M-07） | ⏳ |
| TC-REU-001 | 無介面函式庫 | 低 | I | 驗證腳本皆以無 GUI 方式呼叫核心函式 | ✅ `src/test/verify/` 全部腳本 |
| TC-OTH-001 | 奇數寬高 | 中 | T | 以奇數寬高合成影片封裝 | ⏳ |
| TC-OTH-002 | 介面語言 | 低 | I | 檢查 GUI 文字 | ⏳ |

---

## 7. SRS 範圍外的參考測試（K-1，不計入通過率）

SRS 1.2 將 MultiAudioDownloader 與 i18n／GeoIP 模組列為範圍外；以下結果保留作為觀察紀錄，相關缺陷標記為「範圍外」。

| 編號 | 項目 | 結果 | 缺陷 |
| :--- | :--- | :--- | :--- |
| OOS-I18N-001 | 語系六層決策鏈（注入時區） | 8/8 通過（`env/i18n_layers_log.txt`） | — |
| OOS-I18N-002 | 本機時區判定 | 繁中 Windows 回傳 None | DEF-010 |
| OOS-I18N-003 | IP 鎖定模式 | TypeError；預設開啟 | DEF-003、DEF-005 |
| OOS-DL-001 | 語系清單（yt-dlp 2026.3.17） | 只有 en、en-US | DEF-011 |
| OOS-DL-002 | 多軌下載 | 無 mp3 且回報成功；2026.8.19 對照 3/3 | DEF-011、DEF-012 |
| OOS-ENV-001 | PATH 上的 ffmpeg 不被誤用 | 通過（`env/ffmpeg_source_log.txt`） | — |
| OOS-ENV-002 | Python 3.10 回歸 | 與 3.11 位元級一致（`pixel_jimmy/py310/`）；K-3 後不再必測 | — |

## 8. 摘要（SRS 65 項需求）

| 狀態 | 數量 |
| :--- | ---: |
| ✅ 通過 | 18 |
| ❌ 不通過（含參考） | 11 |
| ◐ 部分／僅參考數據 | 11 |
| ⏳ 未執行 | 25 |
| **合計** | **65** |

依優先序：高優先 44 項中 ✅ 16、❌ 6、◐ 8、⏳ 14。數量由表格解析計算（取每列最後一欄的第一個狀態符號），更新本文件後須重算。

## 附錄：v1.0 → v2.0 編號對照

| v1.0 | v2.0 |
| :--- | :--- |
| TC-ALG-01、02、03、04、05、06 | TC-REL-001、TC-PRF-003／ALG-002、TC-ALG-006、TC-REL-002、TC-ALG-008、TC-ALG-001～004 |
| TC-ALG-07、08 | TC-PRF-001、002、004、005 |
| TC-ALG-09 | TC-ALG-005 |
| TC-PK-01 | TC-REL-002、TC-CNT-003～005 |
| TC-PK-02、03 | TC-CNT-006、007 |
| TC-PK-04 | TC-PCK-002、006、TC-ALG-007 |
| TC-PK-05 | TC-CNT-006 |
| TC-PL-01～03 | TC-PLY-005、006、008、TC-PRF-007、008 |
| TC-PL-04 | TC-CNT-007 |
| TC-PL-05 | TC-PLY-014、TC-REL-003 |
| TC-PL-06、08、TC-DL-01～03 | 範圍外（第 7 節） |
| TC-PL-07 | TC-PLY-009、012 |
| TC-CMP-01 | TC-SEC-002 |
| TC-ENV-01～03 | 範圍外（第 7 節）；TC-ENV-01 併入參考平台驗收 |
| TC-PKG-01、02 | TC-POR-001 |
