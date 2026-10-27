# 系統測試計畫書 (System Test Plan)
## DE 多音軌可逆影音藏密核心系統
### StegoPacker / StegoPlayer / PEE 藏密核心

---

| 文件版本 | 發布日期 | 撰寫者 | 審查者 | 核准者 | 文件狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| v1.0 | 2026-10-26 | QA | — | — | 已作廢（數據不可追溯，見附錄 B） |
| v2.0～v2.1 | 2026-10-27 | QA | — | — | 已取代（範圍與平台與 SRS 不一致） |
| **v3.0** | 2026-10-27 | 李集雋（測試負責人） | 詹皓宇 | 李哲瑋 教授 | **草案**：依 DE-SRS-001 v1.0 與 DE-PEP-001 v3.0 改版（決議 K-1～K-7，見附錄 D） |

**上位文件**：
- DE-SRS-001 v1.0（2026-10-26）：系統需求、驗證方法與追溯矩陣（附錄 A）、待決議問題（附錄 C）。
- DE-PEP-001 v3.0（2026-10-27）：組織、時程、里程碑、測試層級與通過標準（§6.2）。
- 兩者與本文件的逐項對照見 `SRS_PEP_ALIGNMENT.md`。

**狀態標記**：✅ 通過　❌ 不通過　◐ 部分通過或僅有非參考平台數據　⏳ 未執行

**數字可追溯規則**：本文件與測試報告中的每個量測數字，都必須指向 repo 內的驗證腳本與原始 log；log 開頭記錄腳本路徑、腳本 SHA-256、commit 與環境，且不得帶有 `uncommitted changes` 標記。不符合者一律標為 ⏳。

---

## 1. 測試目的與背景 (Objective & Background)

### 1.1 執行目標
1. 依 SRS 第 3 章與附錄 A，逐項驗證 65 項需求；高優先需求全數通過（PEP 6.2.4）。
2. 以可重現的原始 log 驗證核心宣稱：Y 平面位元級還原（REQ-REL-001）、BER = 0（REQ-REL-002）、像素變動 ≤ 1（REQ-PRF-003）。
3. 協助關閉 SRS 附錄 C 嚴重性 H 的 TBD（02、07、08、11），並為 TBD-04、TBD-12 提供量測程序與數據。
4. 以統一的指標定義（MSE-first PSNR、兩段式檔案膨脹）建立可供論文使用的數據（PEP WBS 5.2）。

### 1.2 受測系統 (SUT)
依 SRS 1.2，本系統包含：

| 軟體項目 | 主要原始碼 | 說明 |
| :--- | :--- | :--- |
| StegoPacker | `src/embed_app.py` | 將多條音訊以可逆隱寫嵌入影片 Y 平面，輸出 libx265 lossless HEVC MP4 |
| StegoPlayer | `src/player_app.py` | 背景串流解碼隱藏音軌，多音軌同步播放與即時切換 |
| 藏密核心函式庫 | `src/pee_stego.py`、`src/audio_chunker.py`、`src/stego_facade.py` | Coltuc 低失真 PEE、負載容器（Legacy／DE_CHUNK_V1）、音訊切片與合併 |

系統**不提供**加密、金鑰或簽章（SRS 3.5.3：目標是隱蔽性而非機密性）。

**演算法**
- **主要**：Coltuc 低失真 PEE（IEEE TIP 2012），2×2 區塊整數分散，單像素變動 ≤ 1（SRS REQ-ALG-001～006）。
- **對照基準（論文數據用）**：Traditional Checkerboard PEE，以 `src/test/stego_bench.py` 的實作為準（Q3-R2）。其 skip map 由嵌入端直接交給解碼端、不存於影像內，比較時須註明對其有利。

**與 SRS 不一致之處（測試時以實作行為為準，並回報 SRS v1.1 修訂）**：
- REQ-CNT-006、007：SRS 描述 MP3 以 libmp3lame 重新編碼後以 concat demuxer 合併；目前已改為 MP3 frame 邊界位元組切割與位元組串接（DEF-001／TBD-03，commit `4016071`、`047637d`），合併檔與原檔位元級相同。
- REQ-ALG-005：要求零容量幀寫入可識別標頭，現行可逆機制下不可行（見 `SRS_PEP_ALIGNMENT.md` §3）。

### 1.3 數學模型與指標定義

**(1) 單幀失真與 PSNR**（Y 平面，W×H，第 i 幀）

$$MSE_i = \frac{1}{WH}\sum_{x,y}\left(Y'_i(x,y) - Y_i(x,y)\right)^2,\qquad PSNR_i = 10\log_{10}\frac{255^2}{MSE_i}$$

**(2) 全片 PSNR：一律採 MSE-first**（N 幀）

$$PSNR_{video} = 10\log_{10}\frac{255^2}{\frac{1}{N}\sum_{i=1}^{N} MSE_i}$$

報告須註明 N 的範圍：「全片」或「僅嵌入幀」。**REQ-PRF-001 的「平均 PSNR」須在 SRS v1.1 明定採哪一種**；本計畫建議以「僅嵌入幀的 MSE-first」為驗收值，並同時報告全片值。

**(3) 已廢止算法（僅作對照）**：`stego_bench.py` 取 5 幀、MSE = 0 記 100 dB、再對 dB 取算術平均。會系統性高估 PSNR（同一份資料：舊算法 82.05 dB，全片 MSE-first 61.01 dB；`pixel_jimmy/verify_log.txt`）。

**(4) 離散擴散失真模型** ✅（`src/test/video/images/distortion_model_log.txt`）
- 預測誤差 p = x − (n + w − nw)。可擴張區塊（|p| ≤ 1）嵌入 b：P = 2p + b，d = P − p = p + b ∈ {−1, 0, 1, 2}；平移區塊：d = ±2。
- u = (⌊d/4⌋, ⌊(d+1)/4⌋, ⌊(d+2)/4⌋, ⌊(d+3)/4⌋)，因 |d| ≤ 2，**區塊平方誤差 Σuᵢ² = |d|**（非連續理論的 d²/4）。
- b 均勻隨機時期望 |d|：p = 0 → 0.5；p = +1 → 1.5；p = −1 → 0.5；平移 → 2。
- **每 bit 期望失真（一般式）**：D_exp = 0.5·q₀ + 1.5·q₊ + 0.5·q₋；q₊ = q₋ 時化簡為 **D_exp = 1 − 0.5·q₀**。
- **單幀 MSE** = (N_exp·D_exp + 2·N_shift + SSE_保留列) ÷ (W·H)。

| 實測（9 樣本：Pixel 影片 5 幀、圖片 4 張） | 結果 |
| :--- | :--- |
| Σuᵢ² = \|d\|、u 分配式、max\|Δ\| ≤ 1 | 6,632,602 個處理區塊，0 個不符 |
| SSE 恆等式 | 9/9 逐位元相等 |
| p = ±1 次數對稱差 | 0.048%～0.672%（非全部 < 0.2%） |
| D_exp 模型誤差 | 一般式 −0.51%～+0.33%；對稱近似 −0.67%～+0.27% |
| 模型預測單幀 PSNR vs 實測 | ≤ 0.01 dB |
| 平移區塊佔總 SSE | 7.2%～76.6% |

**(5) 嵌入率**：bpp = payload 位元數 ÷（嵌入幀數 × W × H）；全片 bpp = payload 位元數 ÷（總幀數 × W × H）。α_video = 嵌入幀數 ÷ 總幀數。

**(6) 檔案膨脹（REQ-PRF-004）**：分兩段報告：① 原始來源 → 無損 HEVC 基準檔（未嵌入）；② 無損基準 → stego。REQ-PRF-004 的「位元率增量」對應第 ② 段。

**(7) 已知取捨**：Coltuc 單幀失真低（|Δ| ≤ 1），但在同 payload 下檔案膨脹可能大於 Checkerboard（合成控制組約 1.5～1.8 倍，`synthetic/load_sweep/summary.md`）。不得宣稱 Coltuc 在所有指標上單向全面優勢。

---

## 2. 測試範圍 (Scope)

### 2.1 包含項目 (In-Scope)
SRS 第 3 章全部 65 項需求：

| 類別 | 需求數 | 主要測試方式 |
| :--- | ---: | :--- |
| PCK（StegoPacker） | 12 | GUI 手動；API 自動化 |
| ALG（可逆隱寫演算法） | 9 | 自動化 |
| CNT（負載容器與音訊切片） | 8 | 自動化 |
| PLY（StegoPlayer） | 15 | GUI 探針（半自動）＋手動 |
| PRF（效能） | 10 | 自動化；正式判定在參考平台 |
| REL、AVL、SEC、MNT、POR、REU、OTH | 11 | 自動化、檢查、展示 |

外部介面 IF-SW-05（語系建議模組 → 播放器）只測介面行為：模組不可用時播放器仍依 REQ-PLY-005 選軌。

### 2.2 不包含項目 (Out-of-Scope)
1. **MultiAudioDownloader** 與 **i18n／GeoIP／IP 鎖定模組**（SRS 1.2、PEP 表 1-1；決議 K-1）。已執行的測試與缺陷保留為「範圍外觀察」（`TEST_CASES_SPECIFICATION.md` §7）。
2. **有損轉碼後仍可解碼**（SRS 1.2）。但播放器須平滑降級（REQ-PLY-014、REQ-REL-003），此部分在範圍內。
3. **加密、金鑰、數位簽章**（SRS 1.2）。
4. `for_ip` 儀表板與 benchmarks 實驗工具（SRS 1.2）。
5. 非 Windows 平台。

---

## 3. 測試策略與方法 (Test Strategy & Methodology)

### 3.1 測試層級（PEP 表 6-4）

| 層級 | 內容 | 負責人 | 本計畫的支援 |
| :--- | :--- | :--- | :--- |
| 單元測試 | 預測誤差擴張與還原（REQ-ALG-003、006） | 詹皓宇 | `verify_distortion_model.py` 可作為單元層級的參考實作 |
| 整合測試 | 封裝 → 解碼 → 音軌還原 | 陳宗佑 | `verify_e2e_pack.py`、`verify_jimmy.py`、`verify_audio.py` |
| 系統測試 | 依 SRS 附錄 A 逐項 | 李集雋 | `TEST_CASES_SPECIFICATION.md` v2.0（65 個 TC） |
| 驗收測試 | US-01～US-07 Given/When/Then | 全員 | `MANUAL_TEST_CHECKLIST.md` |

### 3.2 測試案例編號（PEP 6.2.2）
`TC-<類別>-<三位數>`，與 SRS 需求一一對應。完整清單、程序與狀態見 `TEST_CASES_SPECIFICATION.md` v2.0。

### 3.3 優先測試項目（PEP 表 6-5）

| TC | 需求 | 現況 |
| :--- | :--- | :--- |
| TC-REL-001 | 還原 Y 平面逐幀 MD5 一致（TBD-07） | ✅ Pixel 179/179；Xiph 24/24 案例 |
| TC-REL-002 | BER = 0 | ✅ |
| TC-ALG-005 | 含全黑畫面可正常解碼（TBD-11） | ❌ DEF-006 |
| TC-PCK-006 | 超過容量時跳錯且不封裝（TBD-08） | ✅ DEF-007 已修正並驗證（`verify_pck006.py`） |
| TC-REL-003 | 非藏密或被轉檔影片不當機 | ◐ DEF-009 |
| TC-SEC-002 | 一般播放器只看到載體影像與原聲 | ◐ 串流數已驗；播放器待測 |

### 3.4 可逆性與畫質驗收
| 項目 | 標準 | 需求 |
| :--- | :--- | :--- |
| Y 平面還原 | 每個嵌入幀位元級相同 | REQ-REL-001 |
| 像素變動 | max\|Y′ − Y\| ≤ 1 | REQ-PRF-003 |
| U/V 平面 | 不修改 | SRS C-04 |
| payload | BER = 0；MP3 音軌 SHA-256 與原檔相同 | REQ-REL-002（實作優於 SRS 的 ≤ 50 ms） |
| 輸出編碼 | x265 SEI 含 lossless | REQ-ALG-008、DC-02 |
| PSNR | ≥ 55 dB @ 0.20 bpp（算法待 SRS v1.1 明定） | REQ-PRF-001 |
| SSIM | ≥ 0.998 @ 0.20 bpp（⏳ 腳本待加入 SSIM） | REQ-PRF-002 |
| 位元率增量 | ≤ 3% @ 0.20 bpp（**門檻依據有疑義**，見 `SRS_PEP_ALIGNMENT.md` §2） | REQ-PRF-004 |

PSNR 一律同時報告四個值（舊算法、全片 dB 平均、全片 MSE-first、僅嵌入幀 MSE-first）。

### 3.5 效能量測
- **正式判定在 SRS 參考平台**（i7-1185G7，見 5.1）；主要測試機的數據只作參考。
- **執行間變異**：主要測試機上同一輸入、同一 commit，封裝 35.7～205.5 s、擷取 4.7～27.4 s（約 6 倍；`pixel_jimmy/e2e_log.txt`、`py311_rerun/e2e_log.txt`、`py310/e2e_log.txt`），原因為機器狀態而非 Python 版本。因此效能量測須：固定電源模式（接電、最佳效能）並記錄；每項至少 5 次取中位數；不得以單次數字驗收。
- 區分演算法吞吐量（記憶體內）與管線吞吐量（含 FFmpeg 與 I/O）；REQ-PRF-006 指管線。

| 需求 | 門檻 | 主要測試機參考數據 |
| :--- | :--- | :--- |
| REQ-PRF-006 封裝速度 | ≥ 8 fps | 3.5～19 fps |
| REQ-PRF-007 首次發聲 | ≤ 5 s（TBD-04） | 4.0～30.7 s |
| REQ-PRF-008 影音差 | ≤ 450 ms | 最多 4.0 s |
| REQ-PRF-009 GUI 阻塞 | ≤ 200 ms | 0.45～6.5 s |
| REQ-PRF-010 接力 | 無 > 100 ms 靜音或重複 | 跳過 0.65～1.07 s |

### 3.6 回歸測試
`src/test/verify/` 為回歸測試集。修改 `pee_stego.py`、`audio_chunker.py`、`player_app.py`、`stego_facade.py`、`embed_app.py` 的 PR，須附上重跑後的相關 log（PEP 6.4：PR 審查）。11/04 程式凍結後，每個修正 PR 都須重跑 `verify_jimmy.py`、`verify_e2e_pack.py`、`verify_mp3_split.py`。

### 3.7 工具

| 用途 | 腳本 | 對應 TC |
| :--- | :--- | :--- |
| 可逆性、PSNR、無損旗標 | `verify_jimmy.py` | TC-REL-001、ALG-004/006/008、PRF-003 |
| 端到端封裝 | `verify_e2e_pack.py` | TC-REL-002、CNT-003～005 |
| 音訊切片與合併 | `verify_mp3_split.py`、`verify_audio.py`、`verify_chunks.py`、`verify_chunk_boundary.py` | TC-CNT-006、007 |
| 失真模型 | `verify_distortion_model.py` | TC-ALG-001～003 |
| 負載掃描、檔案膨脹 | `verify_load_sweep.py`、`summarize_sweep.py` | TC-PRF-001、004、005 |
| 零容量幀 | `verify_zero_capacity_frames.py` | TC-ALG-005 |
| 封裝邊界 | `verify_packer_edges.py` | TC-PCK-002、ALG-007、CNT-006 |
| 容量超限阻擋 | `verify_pck006.py` | TC-PCK-006 |
| GUI 播放時間線 | `gui_handoff_probe.py` | TC-PLY-002、005～008、014、PRF-007～010 |
| 合成載體 | `gen_synthetic.py` | — |
| 範圍外觀察 | `verify_i18n_layers.py`、`verify_downloader.py`、`verify_ffmpeg_source.py` | §7 |

---

## 4. 測試標準 (Criteria)

### 4.1 進入標準
1. 測試計畫（本文件）經審查（PEP 表 6-6）。
2. `src/test/verify/` 與受測程式碼已 commit；log 標頭乾淨。
3. 載體皆有 `SOURCES.txt` 與 SHA-256（Xiph 四支、確定性合成影片、Pixel 內部素材）。
4. 參考平台（5.1）可用，且已安裝 Python 3.13 與 `requirements.txt`。
5. 決賽版執行檔（PEP M2，11/04）已建置並建立 Git tag。

### 4.2 通過標準（PEP 6.2.4）
1. **高優先需求的 TC 100% 通過。**
2. **中、低優先需求的 TC 通過率 ≥ 90%**，未通過者記錄原因與處理方式。
3. **SRS 附錄 C 嚴重性 H 的 TBD（02、07、08、11）全部關閉。**
4. 效能 TC 在參考平台量測。
5. 測試報告引用的每個數字都對應到乾淨標頭的 log。

### 4.3 缺陷嚴重度
| 等級 | 定義 |
| :--- | :--- |
| Blocker | 崩潰、當機、無法啟動 |
| Critical | 可逆性失敗、payload 損毀、像素變動 > 1 |
| Major | 功能或品質缺陷，核心流程仍可完成 |
| Minor | 顯示或非關鍵行為錯誤 |

### 4.4 程式凍結後的修正原則（PEP M2、R-08）
11/04 之後只修會導致展示失敗的錯誤（決議 K-4）。DEF-002 第一階段修正若能在 11/04 前完成即納入決賽版；否則依上述原則判斷，並在測試報告中列為已知問題或後續工作。

---

## 5. 測試環境與工具 (Environment & Tools)

### 5.1 環境

| 項目 | **參考平台（正式驗收，SRS C-07）** | 主要測試機（已實測，參考數據） | 乾淨環境 |
| :--- | :--- | :--- | :--- |
| 作業系統 | Windows 10 家用版 x64 | Windows 11 Home 26200 | 乾淨 Windows VM（無 Python／FFmpeg） |
| CPU | Intel Core i7-1185G7 @ 3.00 GHz | Intel Core i7-1260P（12C/16T） | — |
| RAM | 16 GB | 15.7 GB | ≥ 8 GB |
| Python | **3.13**（SRS C-02；⏳ 尚未在任何環境實測） | 3.11.5（主要）、3.10.11（已驗證位元級一致） | 打包版不需 Python |
| 主要套件 | 依 `requirements.txt`（numpy 2.4.2、numba 0.65.0、llvmlite 0.47.0、opencv-python 4.13.0.90、PySide6 6.11.1、imageio-ffmpeg 0.6.0、PyInstaller 6.21.0） | 同左 | — |
| FFmpeg | imageio-ffmpeg 內附 7.1；Qt Multimedia 後端 7.1.3 | 同左 | 打包版內附 |
| 負責人 | ⏳ 參考平台的機器持有人待確認 | — | 陳宗佑（打包） |

**版本政策（決議 K-3）**：正式環境為 Python 3.13；Python 3.10 不再必測。`requirements.txt` 中為 3.10 加入的 numpy 環境標記將移除，改為單一 `numpy==2.4.2`（支援 3.13）。

### 5.2 測試資料

| 資料集 | 位置 | 用途 | 授權／限制 |
| :--- | :--- | :--- | :--- |
| Xiph derf 1080p：crowd_run、park_joy、old_town_cross（各 500 幀）、sintel_trailer（1253 幀） | `src/test/video/xiph/`（`SOURCES.txt`） | 正式載體；論文數據 | SVT 三支 CC BY-NC-ND 4.0（不得公開 stego 或修改後影格）；Sintel CC BY 3.0 |
| 確定性合成影片 7 種（含全黑、全白、雜訊） | `src/test/video/synthetic/` | 控制組、TC-ALG-005 | 自製 |
| Pixel 10 廣告（AV1 cover、14 軌 mp3） | `src/test/video/pixel_jimmy/` | 整合與 GUI 測試 | 僅內部測試 |
| 靜態圖片 4 張 | `src/image/` | 失真模型 | repo 內既有 |
| 「測試用黑白片段」（SRS 附錄 D 的 8 部序列） | `src/test/video/drive_bw/`（6 部已檢查） | TBD-07 調查；降級負面測試 | mp4v 有損、5 幀，不可作為可逆性載體 |

媒體檔不進 git（`.gitignore` 只放行 `src/test/video/**/*.txt`）。

### 5.3 缺陷追蹤（決議 K-6）
- 每個缺陷開一個 **GitHub Issue**（PEP 4.5），標註對應的 REQ、TBD、嚴重度與負責人；修正 PR 的說明寫明 Issue 編號。
- `DEFECT_LOG.md` 保留詳細證據（現象、根本原因、log、重現步驟、限制），並記錄 Issue 編號；兩者狀態須一致。

---

## 6. 資源與角色分工（PEP 3.2、表 3-1）

| 成員 | 測試相關職責 |
| :--- | :--- |
| **李集雋**（文件與品質負責人） | 測試計畫與執行（A/R）；系統測試；測試報告；維護 TC 與缺陷紀錄 |
| **詹皓宇**（專案與技術負責人） | 單元測試；核心演算法缺陷修正（DEF-006、DEF-007 等）；效能與可逆性實驗（A/R）；測試計畫審查 |
| **陳宗佑**（播放端負責人） | 整合測試；StegoPlayer 缺陷修正（DEF-002、DEF-009）；執行檔打包；TBD-04、TBD-12 量測 |
| **李哲瑋 教授** | 文件核准；重大範圍與規格決策 |

驗收測試（US-01～US-07）由全員執行。

---

## 7. 時程（PEP 4.2～4.4）

| 期間 | 工作 | PEP 對應 | 出口 |
| :--- | :--- | :--- | :--- |
| 10/27～11/03 | 先行測試（本分支已完成大部分自動化與缺陷登記）；DEF-007 修正驗證；TBD-07 重跑可逆性（Xiph） | WBS 1.1、1.5 | 可逆性驗證結果 |
| **11/04** | **決賽版程式凍結、建立 tag**；凍結版回歸 | M2 | TBD-01、02、08、11 關閉 |
| 11/07 | 全國決賽 | M3 | — |
| 11/09～11/15 | 測試計畫定稿；參考平台與 Python 3.13 環境建立 | WBS 2.2 | 本文件核准 |
| 11/16～11/29 | 系統測試執行（參考平台）；效能量測（TBD-04、12） | WBS 2.3、3.1 | 測試報告 |
| **11/29** | **測試計畫與報告繳交（D-04）** | M5 | 高優先 TC 全數通過 |

**估算**：參考平台上 Xiph 四支載體的負載掃描約需 1.5～2 小時（主要測試機實測，視機器狀態）；GUI 探針每支約 1 分鐘，效能項目每項 5 次。

---

## 8. 風險管理

與 PEP 表 4-7 對應；本計畫另增測試專屬風險。

| 編號 | 風險 | PEP | 狀態 | 因應 |
| :--- | :--- | :--- | :--- | :--- |
| RSK-01 | 極端內容（全黑、全白、高雜訊）導致無法解碼 | R-02 | **已發生**（DEF-006／TBD-11） | Demo 影片事先實測；合成載體納入極端內容 |
| RSK-02 | 可逆性驗證重跑失敗 | R-01 | Pixel 已通過；Xiph 執行中 | TBD-07 以 Xiph 重驗 |
| RSK-03 | 決賽電腦無法執行（缺解碼器、權限、效能） | R-03 | — | 乾淨 VM 驗收（TC-POR-001）；HEVC 擴充功能列為前置條件 |
| RSK-04 | 擷取速度不足造成播放卡頓、不同步 | — | **已發生**（DEF-002） | Demo 使用短片；效能於參考平台重測 |
| RSK-05 | 測試資料遺失、數字無法重現 | R-09 | v1.0 已發生 | `SOURCES.txt`＋SHA-256；確定性合成腳本 |
| RSK-06 | 依賴版本漂移 | — | 已發生 | log 記錄所有版本；MP3 改位元組切割 |
| RSK-07 | 回歸未被攔截 | R-08 | 已發生（`a5919e0`） | PR 須附重跑 log |
| RSK-08 | 文件與實作不一致 | R-05 | 已發生（SRS REQ-CNT-006/007、REQ-ALG-005、附錄 D） | 回報 SRS v1.1（WBS 2.4） |
| RSK-09 | 素材授權 | — | — | 論文只報數字與原始影格；SVT 不公開 stego |
| RSK-10 | **效能門檻依據有疑義**（REQ-PRF-001、004 取自有損 mp4v 檔） | R-05 | 新發現 | `SRS_PEP_ALIGNMENT.md` §2；以 Xiph 無損數據重訂 |
| RSK-11 | **參考平台不可得** | R-09 | ⏳ | 若無 i7-1185G7，需 SRS v1.1 改定參考平台 |

---

## 9. 測試可交付成果（PEP D-04）

| 交付物 | 位置 | 狀態 |
| :--- | :--- | :--- |
| 系統測試計畫書 | `SYSTEM_TEST_PLAN.md` | v3.0 草案 |
| 測試案例規格書 | `TEST_CASES_SPECIFICATION.md` | v2.0（65 個 TC，依 SRS 編號） |
| SRS／PEP 對照 | `SRS_PEP_ALIGNMENT.md` | v0.1 |
| 手動測試檢核表 | `MANUAL_TEST_CHECKLIST.md` | v1 |
| 驗證腳本 | `src/test/verify/` | 已 commit（`047637d`）；`verify_downloader.py` 待 commit |
| 原始 log 與資料來源 | `src/test/video/*/` | 部分 log 待以乾淨 commit 重跑 |
| 缺陷紀錄 | `DEFECT_LOG.md`＋GitHub Issues | 12 筆；範圍內 7 筆已開 Issue #18～#24 |
| 缺陷修正建議 | `FIX_PROPOSALS.md` | v0.1 |
| 測試報告 | `TEST_SUMMARY_REPORT.md` | v0.1 骨架；11/29 定稿 |

### 9.1 缺陷摘要

| ID | 標題 | 嚴重度 | SRS 需求／TBD | 範圍 | 狀態 |
| :--- | :--- | :---: | :--- | :---: | :--- |
| DEF-001 | 分塊合併切點插入 31.6 ms 靜音 | Major | REQ-CNT-006/007、REL-002／TBD-03 | 內 | Fixed |
| DEF-002 | 分塊串流播放無法維持影音同步 | Major | REQ-PLY-002/005/006/008、PRF-007～010／TBD-09 | 內 | Open |
| DEF-003 | IP 鎖定策略 TypeError | Major | — | 外 | Open（暫緩） |
| DEF-004 | chunk0 回報總時長為整首長度 | Minor | REQ-PLY-006（間接） | 內 | Open |
| DEF-005 | IP 鎖定預設開啟 | Major | — | 外 | Open（暫緩） |
| DEF-006 | payload 跨越零容量幀時無法擷取 | **Critical** | REQ-ALG-005、REL-002／TBD-11 | 內 | Open |
| DEF-007 | 容量超限分支 NameError | Minor | REQ-PCK-006／TBD-08（SRS 評為 H） | 內 | Fixed（待 PR 合併） |
| DEF-008 | 容量不足要等全片編碼後才報錯並留下殘檔 | Minor | REQ-PCK-006、011 | 內 | Open |
| DEF-009 | chunk0 之後才失敗時播放卡住 | Major | REQ-PLY-014、REL-003 | 內 | Open |
| DEF-010 | 非英文 Windows 時區判定失效 | Major | — | 外 | Open |
| DEF-011 | 鎖定的 yt-dlp 取不到配音音軌 | Major | — | 外 | Open（暫緩） |
| DEF-012 | 下載器靜默略過缺少的語系 | Minor | — | 外 | Open |

---

## 附錄 A：Phase 3 驗證項目狀態（論文數據）

| # | 項目 | 狀態 | 證據 |
| :--- | :--- | :---: | :--- |
| P3-1～P3-3 | 像素變動、影像還原、payload 通道 | ✅ | `pixel_jimmy/verify_log.txt` |
| P3-4 | 音軌位元級相同（MP3） | ✅ | `pixel_jimmy/e2e_log.txt` |
| P3-5 | 舊 PSNR 算法高估 | ✅ | `pixel_jimmy/verify_log.txt` |
| P3-6 | 單幀飽和 PSNR | ✅ | SVT 51.62～51.69 dB、sintel 55.51 dB、Pixel 54.96 dB、圖片 52.52～53.52 dB（A.3） |
| P3-7、P3-8 | 失真模型 | ✅ | `images/distortion_model_log.txt` |
| P3-9 | PSNR 對負載 | ✅ | A.3、`xiph/load_sweep/summary.md` |
| P3-10 | 兩段式檔案膨脹 | ✅ | A.3（sintel 第一段不可採用） |
| P3-11 | 舊報告 90.83／81.55／62.92 | 結案：無法重現 | 載體遺失 |
| P3-12 | 切點 30 ms 偏移 | ✅ 已修正 | DEF-001 |

### A.1 Pixel 載體實測（`pixel_jimmy/verify_log.txt`）
1920×1080、720 幀；payload 80,725,184 bits；嵌入 179 幀（α_video ≈ 24.9%）。單幀 PSNR 54.77～56.00 dB；MSE-first 嵌入幀 54.96 dB、全片 61.01 dB；舊算法 82.05 dB；0.2175 bpp（嵌入幀）。單一有損 AV1 來源，不能一般化。

### A.2 合成控制組（`synthetic/load_sweep/summary.md`）
全部可嵌入案例可逆；Coltuc 每幀約 0.249 bpp、Checkerboard 約 0.99 bpp；noise、black、white 對 Coltuc 為零容量；同 payload 1024 KiB 時全片 PSNR 差 −0.002～+0.89 dB，Coltuc 檔案膨脹為 Checkerboard 的 1.5～1.8 倍。只作控制組。

### A.3 Xiph 正式載體（`src/test/video/xiph/load_sweep/summary.md`，commit `047637d`）
4 支載體（SVT 三支各 500 幀；sintel 取前 500 幀）× 2 方法 × 6 案例，共 48 案例。

| 項目 | crowd_run | park_joy | old_town_cross | sintel_trailer |
| :--- | ---: | ---: | ---: | ---: |
| Coltuc 容量（bpp） | 0.0494 | 0.0436 | 0.0448 | 0.2234 |
| Checkerboard 容量（bpp） | 0.3036 | 0.2725 | 0.2825 | 0.9132 |
| Coltuc 單幀飽和 PSNR（滿載，MSE-first） | 51.69 dB | 51.62 dB | 51.63 dB | 55.51 dB |
| Coltuc 滿載「無損基準→stego」 | +1.15% | +1.18% | +1.50% | +35.88% |
| 同 payload 4096 KiB 全片 PSNR（Coltuc／CB） | 53.44／52.67 | 52.94／54.09 | 53.05／52.33 | 65.66／66.02 |
| 同 payload 4096 KiB 膨脹（Coltuc／CB） | +0.76%／+0.67% | +0.86%／+0.65% | +1.08%／+0.93% | +5.64%／+3.75% |
| Coltuc 可逆（6 案例） | 6/6 | 6/6 | 6/6 | 6/6 |

**結論**：
1. **可逆性**：Coltuc 24/24 案例 restore_fail = 0、payload 位元相等（TC-REL-001、TBD-07）。
2. **REQ-PRF-005 不成立**：三支自然場景 SVT 序列的 Coltuc 容量只有 0.044～0.049 bpp（< 0.15）。Pixel 廣告的 0.2175 bpp 推測來自 AV1 有損來源的去雜訊效果，不代表一般攝影素材。
3. **REQ-PRF-004 不成立**：唯一能達到約 0.20 bpp 的 sintel，滿載時膨脹 +35.88%（門檻 ≤ 3%）；SVT 只到 +1.2～1.5%，但無法達到 0.20 bpp。
4. **REQ-PRF-001**：只有 sintel 能達到約 0.22 bpp，此時嵌入幀 MSE-first 55.51 dB（≥ 55）；SVT 無法在 0.20 bpp 量測。
5. **Coltuc vs Checkerboard（同 payload）**：全片 PSNR 互有高低（−1.15～+0.77 dB）；檔案膨脹 4/4 為 Coltuc 較大。單幀 PSNR Coltuc 高約 8 dB（51.7 vs 43.2），但同 payload 需分散到更多幀。**不支持「Coltuc 全面優於 Checkerboard」**。
6. **Checkerboard 100% 負載**：crowd_run、old_town_cross 的 payload_ok = False，但 restore_fail = 0。以 `bf05120` 重查（`xiph/load_sweep/cb_full_recheck/`）：實際嵌入 314,799,777／314,805,772 與 292,884,313／292,885,508 位元（約 99.998%），已嵌入者全部正確取回（extracted_ok = True）。**確認為 Checkerboard 容量隨嵌入資料變動所致，非可逆性失敗。**
7. **限制**：sintel 只用前 500 幀，「來源→基準」一段（−95.37%）不可採用；Checkerboard 的 skip map 不存於影像內，比較對其有利。

---

## 附錄 B：v1.0 作廢項目

| v1.0 內容 | 處理 | 原因 |
| :--- | :--- | :--- |
| 「無損」「資訊安全」「解密」用語 | 改寫 | 系統無金鑰；無損僅限 Y 平面與 payload |
| 單位元方均失真 ∼ p²/4 | 刪除 | 與 Σuᵢ² = \|d\| 不符 |
| PSNR ≥ 90 dB（10%）、≥ 60 dB（80%） | 刪除 | 舊算法、載體遺失；改以 REQ-PRF-001 |
| SSIM ≥ 0.997 | 改為 REQ-PRF-002（≥ 0.998） | 依 SRS |
| 解密 ≥ 240 FPS | 改寫 | 演算法吞吐量不代表管線；改以 REQ-PRF-006 |
| `libx265 crf 0` | 更正 | 實際為 `lossless=1` |
| Zhang-Zeng-Ou 2D HS | 移出範圍 | TBD-02 處理 |
| 語系與 IP 自動匹配 | 移出範圍 | SRS 1.2（K-1） |
| RTX 40／CUDA | 刪除 | 程式未使用 GPU |
| 4 週時程 | 改寫 | 依 PEP |

---

## 附錄 C：重現指令

從 repo 根目錄執行；`<D>` = `src/test/video/pixel_jimmy`。

```
python src/test/verify/verify_jimmy.py          <D> > <D>/verify_log.txt
python src/test/verify/verify_audio.py          <D> > <D>/audio_log.txt
python src/test/verify/verify_chunks.py         <D> --initial-sec 3.0 > <D>/chunk_log_3s.txt
python src/test/verify/verify_chunk_boundary.py <D> > <D>/boundary_log.txt
python src/test/verify/verify_mp3_split.py      <D> > <D>/mp3_split_log.txt
python src/test/verify/verify_e2e_pack.py       <D> > <D>/e2e_log.txt
python src/test/verify/gui_handoff_probe.py     <D>/e2e_stego.mp4 <D>/gui_probe > <D>/gui_probe/gui_probe_log.txt
python src/test/verify/verify_distortion_model.py --video <D>/cover.webm --frames 0 144 288 432 576 --image src/image/cat.jpg src/image/DE.jpg "src/image/PEE Stego.jpg" src/image/SEM_0420.JPG > src/test/video/images/distortion_model_log.txt
python src/test/verify/gen_synthetic.py src/test/video/synthetic
python src/test/verify/verify_zero_capacity_frames.py src/test/video/synthetic <D>/audio_de-DE.mp3 src/test/video/synthetic/zero_cap > src/test/video/synthetic/zero_cap_log.txt
python src/test/verify/verify_load_sweep.py src/test/video/xiph/<seq>.y4m --loads 10 40 80 100 --payload-kib 1024 4096 --encode > src/test/video/xiph/load_sweep/<seq>_log.txt
```

---

## 附錄 D：決議紀錄

| ID | 決議（2026-10-27） | 取代 |
| :--- | :--- | :--- |
| K-1 | 範圍以 SRS 為準：下載器與 i18n／GeoIP 移出；DEF-003、005、011 的修正暫緩，只修 DEF-007 | Q4-4（Node.js、外部 FFmpeg）、Q4-5（語系規格） |
| K-2 | 參考平台以 SRS C-07 為準（Win10、i7-1185G7、16 GB）；主要測試機數據為參考 | Q4-1、Q4-2 |
| K-3 | Python 以 SRS C-02 為準（3.13）；3.10 不再必測，移除 numpy 環境標記 | Q4-3 |
| K-4 | 依 PEP 於 11/04 程式凍結；測試報告 11/29 繳交 | Q6 |
| K-5 | TC 編號依 PEP 6.2.2（SRS 類別＋三位數） | — |
| K-6 | 缺陷以 GitHub Issues 追蹤，`DEFECT_LOG.md` 記錄證據與 Issue 編號；開 Issue 前先列清單確認 | Q5b |
| Q3-R2 | Checkerboard 對照以 `stego_bench.py` 為準 | — |
| Q4-6 | Windows 媒體播放器；HEVC 擴充功能列為前置條件（併入 TC-SEC-002） | — |
| Q4-7 | 正式載體：Xiph 四支＋確定性合成影片 | — |

---
*本文件為 v3.0 草案，依 PEP 表 6-6 經詹皓宇審查後生效。*
