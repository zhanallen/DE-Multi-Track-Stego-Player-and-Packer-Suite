# SRS／PEP 對照與測試覆蓋分析

| 版本 | 日期 | 依據 | 狀態 |
| :--- | :--- | :--- | :--- |
| v0.1 | 2026-10-27 | DE-SRS-001 v1.0（2026-10-26）、DE-PEP-001 v3.0（2026-10-27）、本 repo 分支 `bugfix/def-001-007-qa-suite` | 草案，待組內決議 |

SRS 1.1 規定測試人員「依第 3 章需求與附錄 A 追溯矩陣設計測試案例」；PEP 6.2.2 規定測試案例編號為 `TC-<類別>-<三位數>`，類別與 SRS 需求一致。本文件比對目前 `SYSTEM_TEST_PLAN.md` v2.1 與兩份文件的差異，並列出 SRS 每項需求目前已有的測試證據。

---

## 1. 需要決議的衝突

| # | 項目 | SRS／PEP | 目前 STP v2.1 | 影響 |
| :---: | :--- | :--- | :--- | :--- |
| **K-1** | **範圍** | SRS 1.2、PEP 表 1-1：**不含** MultiAudioDownloader 與 i18n／GeoIP／IP 鎖定模組；播放器只需接收「建議音軌」介面（IF-SW-05） | MOD-DL 與語系六層邏輯列在 In-Scope（Q4-5） | DEF-003、005、010、011、012 屬 SRS 範圍外；TC-DL、TC-PL-06、TC-PL-08 應移出或改為「參考測試」 |
| **K-2** | **參考平台** | SRS C-01、C-07、PEP 4.7：Windows 10 家用版、**Intel Core i7-1185G7**、16 GB；效能門檻（REQ-PRF-006～010）以此平台量測 | Win11 必測、Win10 參考（Q4-1）；**i7-1260P** 為最低支援規格（Q4-2） | 本機的效能數字不能直接判定 REQ-PRF 是否通過；需在 i7-1185G7 平台重測 |
| **K-3** | **Python 版本** | SRS C-02、PEP 5.2：**Python 3.13**；TBD-10：實際開發環境為 3.13.2 | 3.10 與 3.11 必測（Q4-3）；全部實測在 3.11.5／3.10.11 | 正式環境 3.13 完全沒有實測；3.10 的鎖版工作與 SRS 不一致 |
| **K-4** | **時程與程式凍結** | PEP M2：**11/04 決賽版程式凍結**，凍結後只修會導致展示失敗的錯誤；測試執行 11/16～11/29；測試報告 11/29 | DEF-002 必修，可延後交付（Q6b）；交付日 11/27 | DEF-002 修正若在 11/04 後進行，需確認是否屬「會導致展示失敗」；交付日應改為 11/29 |
| **K-5** | **測試案例編號** | PEP 6.2.2：`TC-<類別>-<三位數>`，與 SRS 類別一致（TC-REL-001 對應 REQ-REL-001） | `TC-ALG-01`、`TC-PK-01` 等自訂編號 | 需改編號並依 SRS 附錄 A 重建追溯 |
| **K-6** | **缺陷追蹤** | PEP 4.5：每個 TBD 與 bug 開 **GitHub Issue** | `DEFECT_LOG.md` 為唯一紀錄、不同步外部（Q5b） | 需決定是否改為 Issue，或 DEFECT_LOG 對照 Issue 編號 |
| **K-7** | **效能門檻的依據** | SRS 3.3：REQ-PRF-001（PSNR ≥ 55 dB）、REQ-PRF-004（位元率增量 ≤ 3%）取自 `video_benchmark_results.json` 的 8 部序列 | — | 見第 2 節：該資料來源有問題，門檻需要重新檢討 |

## 2. TBD-07 的可能成因（新證據）

SRS 附錄 D 的 8 部測試序列（Real_Nature、Urban_City、Conference、Surveillance、Synthetic_Graphics、Foreman、Mobile、Bus），與雲端資料夾「測試用黑白片段」的檔名完全一致。本計畫已檢查其中 6 部（`src/test/video/drive_bw/probe_log.txt`、`ydiff_log.txt`）：

- cover 與 stego 都是 **MPEG-4 Part 2（`mp4v`）有損編碼**，每部只有 5 幀；
- stego 與 cover 的 Y 差值最大到 14～22（Coltuc 保證 ≤ 1），每幀標頭都已損毀。

這可以解釋 TBD-07：結果檔中 Coltuc 全部 `is_reversible = False` 是**正確的**（載體經有損再編碼後本來就無法還原）。同時也代表：

- REQ-PRF-001 的「PSNR 55.05–56.97 dB」、REQ-PRF-004 的「位元率增量 2.08–2.10%」**是在有損 `mp4v` 檔案上量到的**，不是 libx265 lossless 的結果，不能作為門檻依據。
- 以本計畫的無損實測，合成控制組在同 payload 下的「無損基準 → stego」膨脹達數百到數萬 %（`synthetic/load_sweep/summary.md`），**REQ-PRF-004 的 ≤ 3% 極可能無法達成**；正式數字待 Xiph 載體掃描完成。
- PEP 4.7 寫「Xiph.org 標準測試影片 8 部（見 SRS 附錄 D）」，但附錄 D 的 8 部中只有 Foreman、Mobile、Bus 是常見標準序列，其餘不是 Xiph 的檔案。

此推論尚未比對 `video_benchmark_results.json` 本身（該檔不在本 repo），需向產生者確認。

**Xiph 無損實測佐證（2026-10-27，`xiph/load_sweep/summary.md`）**：唯一能達到約 0.20 bpp 的 sintel，滿載時「無損基準→stego」膨脹 +35.88%；自然場景 SVT 的 Coltuc 容量只有 0.044～0.049 bpp，無法達到 0.20 bpp。因此 REQ-PRF-004（≤ 3%）與 REQ-PRF-005（≥ 0.15 bpp）在無損實測下均不成立，建議 SRS v1.1 以本數據重訂門檻或改寫量測條件。

## 3. TBD 與缺陷對照

| SRS TBD | 嚴重性 | 對應 | 狀態 |
| :--- | :---: | :--- | :--- |
| TBD-01 首塊長度不一致（封裝 6 s、播放 3 s） | M | 未登記為 DEF；實測時 `chunked_stego.mp4` 以 3.0 s 封裝 | 建議登記 |
| TBD-02 zhang_zeng_ou_hs 靜默改用 Coltuc | H | 未登記；每次執行皆出現 `hevc_rdh_core` 載入警告 | 建議登記 |
| TBD-03 串流模式重新編碼音訊 | M | **= DEF-001**，已以位元組切割修正（`4016071`、`047637d`） | 已修正；SRS REQ-CNT-006、007、REL-002 需改寫（v1.1） |
| TBD-04 首次發聲時間未量測 | M | 本機已量（慢 30.7 s、快 4.0 s，`gui_probe_log.txt`）；非參考平台 | 需在參考平台重測 |
| TBD-05 無匯出還原影片 | M | — | 屬功能決策 |
| TBD-06 未檢查奇數寬高 | L | 未測 | 可補 TC-OTH-001 |
| TBD-07 結果檔與報告矛盾 | H | 見第 2 節；可逆性已以 Pixel 載體實測通過（179/179） | Xiph 掃描完成後補強 |
| TBD-08 容量超限 NameError | H | **= DEF-007** | 已同意修正 |
| TBD-09 GUI 執行緒同步執行 | M | 部分對應 **DEF-002**（停滯 0.45～6.5 s） | — |
| TBD-10 Python 版本 | L | 見 K-3 | — |
| TBD-11 低容量幀無法解碼 | H | **= DEF-006**（另發現高雜訊幀同樣零容量） | Open；不由 QA 修正（PEP WBS 1.2 由詹皓宇負責） |
| TBD-12 效能門檻無量測 | M | 本機已有數據；見 K-2 | 需在參考平台重測 |

**REQ-ALG-005 的可行性問題**：要求「低容量幀仍寫入 n_chunk = 0 的可識別標頭」。但完全零容量的幀（全黑、全白、高雜訊）連標頭被覆蓋的原始 LSB 都無處可存，依現行可逆機制無法寫入標頭。建議 SRS v1.1 改寫此需求，或採 `FIX_PROPOSALS.md` 的方案 A（標頭加 magic 與 CRC，解碼端驗證失敗即視為略過幀）。

**SRS 範圍外的缺陷**：DEF-003、005、010（i18n）、DEF-011、012（下載器）。

## 4. SRS 需求的測試覆蓋現況

狀態：✅ 已有證據通過　❌ 已有證據不通過　◐ 部分　⏳ 尚無證據。證據路徑相對於 `src/test/video/`。

| 需求 | 名稱 | 優先 | 狀態 | 證據／說明 |
| :--- | :--- | :---: | :---: | :--- |
| REQ-PCK-001～005 | 載體選擇、容量預估、音軌管理、使用率 | 高/中 | ⏳ | GUI 未測；容量估計值已比對（`packer/packer_edges_log.txt`：低估 0.1～14.4%） |
| REQ-PCK-006 | 容量超限阻擋 | 高 | ❌ | DEF-007（TBD-08） |
| REQ-PCK-007～012 | 輸入驗證、演算法選擇、串流選項、背景封裝、結果通知、輸出路徑 | — | ⏳ | GUI 未測 |
| REQ-ALG-001～003 | 預測、處理帶、擴張與四等分散 | 高 | ✅ | `images/distortion_model_log.txt`（6,632,602 區塊 0 不符） |
| REQ-ALG-004 | 每幀標頭與旁通道 | 高 | ✅ | `pixel_jimmy/verify_log.txt`、`distortion_model_log.txt`（SSE 恆等式含保留列） |
| REQ-ALG-005 | 低容量幀略過 | 中 | ❌ | DEF-006（TBD-11）；需求本身可行性待議 |
| REQ-ALG-006 | 提取與還原 | 高 | ✅ | `pixel_jimmy/verify_log.txt`（179/179） |
| REQ-ALG-007 | 容量估算方法 | 中 | ◐ | 實作符合描述；估計值偏低（`packer_edges_log.txt`） |
| REQ-ALG-008 | 輸出編碼 lossless | 高 | ✅ | `verify_log.txt`（SEI 含 lossless） |
| REQ-ALG-009 | 管線化處理 | 中 | ⏳ | 未檢查 |
| REQ-CNT-001～005 | 長度標頭、Legacy、DE_CHUNK_V1、Chunk、狀態機 | 高 | ✅ | `e2e_log.txt`、`audio_log.txt`、`synthetic/zero_cap_log.txt`（Legacy 與分塊皆有執行） |
| REQ-CNT-006、007 | 音訊切片與合併 | 高 | ◐ | 已改為位元組切割（DEF-001 修正），**與 SRS 現行描述不同**；`mp3_split_log.txt` |
| REQ-CNT-008 | 語系 ID 解析 | 中 | ◐ | 間接驗證（e2e 以 `*_audio_<lang>` 命名，14/14 正確） |
| REQ-PLY-001 | 開啟藏密影片 | 高 | ◐ | 探針以 API 載入；命令列與對話框未測 |
| REQ-PLY-002 | 背景串流解碼（GUI 阻塞 ≤ 200 ms） | 高 | ❌ | 停滯 0.45～6.5 s（DEF-002） |
| REQ-PLY-003、004 | 緩衝 HUD、音軌清單 | 中/高 | ⏳ | — |
| REQ-PLY-005 | 首塊自動開播 | 高 | ❌ | DEF-002 |
| REQ-PLY-006 | 無縫接力 | 高 | ❌ | DEF-002（跳過 0.65～1.07 s） |
| REQ-PLY-007 | 緩衝不足等待 | 中 | ✅ | 依規格暫停並恢復（`gui_probe_log.txt`）；但造成 16.3 s 暫停 |
| REQ-PLY-008 | 影音同步校正 | 高 | ❌ | chunk0 期間不校正，落後最多 4.0 s |
| REQ-PLY-009～013 | 熱切換、待播、載體靜音、控制、裝置跟隨 | — | ⏳ | `MANUAL_TEST_CHECKLIST.md` M-03 |
| REQ-PLY-014 | 解碼失敗備援 | 高 | ◐ | 有損轉碼正常；chunk0 後失敗卡住（DEF-009） |
| REQ-PLY-015 | 暫存檔清理 | 高 | ⏳ | — |
| REQ-PRF-001 | PSNR ≥ 55 dB @ 0.20 bpp | 高 | ◐ | Pixel 嵌入幀 MSE-first 54.96 dB @ 0.2175 bpp；需在 0.20 bpp 量測並定義「平均」算法 |
| REQ-PRF-002 | SSIM ≥ 0.998 | 高 | ⏳ | 目前腳本未算 SSIM |
| REQ-PRF-003 | 像素變動 ≤ 1 | 高 | ✅ | 多份 log |
| REQ-PRF-004 | 位元率增量 ≤ 3% | 中 | ❌ | sintel 0.2234 bpp：+35.88%（`xiph/load_sweep/summary.md`） |
| REQ-PRF-005 | 容量 ≥ 0.15 bpp | 中 | ❌ | SVT 自然場景 0.044～0.049 bpp |
| REQ-PRF-006～010 | 封裝速度、首次發聲、同步、GUI、接力 | — | ❌／⏳ | 本機數據多數不達標，但非參考平台（K-2） |
| REQ-REL-001 | 載體可逆還原 | 高 | ✅ | Pixel 179/179；Python 3.10／3.11 一致 |
| REQ-REL-002 | 負載正確性 | 高 | ✅ | BER = 0；MP3 SHA-256 相同（優於 SRS 的「時長差 ≤ 50 ms」） |
| REQ-REL-003 | 異常輸入容錯 | 高 | ◐ | 同 REQ-PLY-014 |
| REQ-AVL-001 | 離線運作 | 高 | ⏳ | — |
| REQ-SEC-001 | 暫存資料範圍 | 中 | ⏳ | — |
| REQ-SEC-002 | 一般播放器隱蔽性 | 高 | ◐ | `e2e_stego.mp4` 串流為 1 HEVC（hvc1）+ 1 AAC（`pixel_jimmy/gui_probe/gui_probe_log.txt` 開頭的 ffmpeg 串流資訊）；第三方播放器未測 |
| REQ-MNT-001、REU-001 | 外觀介面、無介面函式庫 | 中/低 | ◐ | 驗證腳本皆以無 GUI 方式呼叫核心函式（REU-001 實質已滿足） |
| REQ-POR-001 | 免安裝執行檔 | 高 | ⏳ | 需乾淨 VM |
| REQ-OTH-001 | 奇數寬高 | 中 | ⏳ | — |
| REQ-OTH-002 | 介面語言 | 低 | ⏳ | — |

## 5. 建議

1. 先就 K-1～K-7 做出決議；之後把 `SYSTEM_TEST_PLAN.md` 改版為 v3.0，章節與測試案例全部以 SRS 附錄 A 為骨架，並採 PEP 6.2.2 的編號。
2. `DEFECT_LOG.md` 每筆缺陷加上對應的 REQ 與 TBD 編號。
3. 參考平台（i7-1185G7）與 Python 3.13 的實測排入 PEP WBS 2.3（11/16～11/29）。
4. 第 2 節的推論需請效能實驗負責人（詹皓宇）確認，作為 TBD-07 的處理依據。
