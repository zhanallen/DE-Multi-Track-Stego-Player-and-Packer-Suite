# 系統測試計畫書 (System Test Plan)
## 低變換失真預測誤差擴張多音軌播放與封裝套件
### Low-Distortion PEE Multi-Track Stego Packer & Player Suite

---

| 文件版本 | 發布日期 | 撰寫者 / 職稱 | 審核者 / 職稱 | 文件狀態 |
| :--- | :--- | :--- | :--- | :--- |
| v1.0 | 2026-10-26 | QA Lead | 專題指導教授 / PM | 已作廢（數據不可追溯，見附錄 B） |
| v2.0 | 2026-10-27 | QA Lead | 專題指導教授 / PM | 草案 |
| **v2.1** | 2026-10-27 | QA Lead | 專題指導教授 / PM | **待核准**：Phase 4–6 訪談完成（附錄 D）；剩餘 ⏳ 為待實測、待下載或待填寫項目 |

**狀態標記**：✅ 已實測通過　❌ 實測不通過　🟡 據報已驗證、原始 log 待補　⏳ 待確認／待實測（Pending）

**數字可追溯規則**：本文件中每一個量測數字，都必須指向 repo 內的驗證腳本與其原始 log；log 開頭須記錄腳本路徑、腳本 SHA-256 與 commit，且不得帶有 `uncommitted changes` 標記。不符合者一律標為 ⏳。

---

## 1. 測試目的與背景 (Objective & Background)

### 1.1 執行目標
1. 驗證三個 GUI 子系統與演算法核心在 Windows 桌面環境下的端到端功能。
2. 以可重現的原始 log，驗證核心技術宣稱：影像可逆還原、像素變動上限、payload 通道無損、音軌位元級還原。
3. 以統一的指標定義（MSE-first PSNR）建立畫質與檔案膨脹的量測基準，取代 v1.0 中不可追溯的數字。
4. 建立缺陷紀錄與回歸測試集，作為後續修正與論文數據的依據。

### 1.2 受測系統 (SUT) 概述
本套件以**可逆資料隱寫 (Reversible Data Hiding, RDH)** 將多軌語系音訊藏入影片的亮度 (Y) 通道，播放時即時擷取並還原原始畫面。系統**無加解密金鑰機制**；隱藏的目的是封裝與相容性（一般播放器仍可當普通影片播放），而非保密。

| 子系統 | 進入點 | 主要功能 |
| :--- | :--- | :--- |
| **MultiAudioDownloader** | `src/download_app.py` | 以 `yt-dlp` + Node.js 解析串流平台影片的多語系音軌並下載 |
| **StegoPacker** | `src/embed_app.py` | 估算容量、將多軌音訊分塊封裝（Manifest → Chunk0 → Chunk1）、以 Coltuc PEE 嵌入、輸出 x265 無損 HEVC (`lossless=1`) |
| **StegoPlayer** | `src/player_app.py` | 背景執行緒逐幀擷取並還原、先播 Chunk0 再切換完整音軌、語系自動選軌、解碼失敗時平滑降級播放載體原音 |
| **演算法核心** | `src/pee_stego.py`、`src/stego_facade.py`、`src/audio_chunker.py`、`src/i18n_detector.py` | Coltuc 2×2 PEE（JPEG4 預測、skip-map、標頭保留列）、音訊分塊、語系判定 |

**演算法**
- **主要**：Coltuc 低變換失真 PEE（IEEE TIP 2012），2×2 區塊整數分散，單一像素變動嚴格 ≤ ±1。
- **對照基準**：Traditional Checkerboard PEE，以 `src/test/stego_bench.py` 的實作（`checkerboard_embed_frame_jit` 等）為準（Q3-R2）。該實作不走封裝管線，量測檔案膨脹時須將其輸出幀以與主程式相同的 x265 參數（`-preset ultrafast -x265-params lossless=1 -pix_fmt yuv420p`）編碼，確保可比。

**語系判定規格（Q4-5，2026-10-27 確認）**：採**六層決策邏輯**，依序整合使用者歷史偏好、系統語言、時區與 GeoIP；前一層命中即決定，未命中才往下一層。順序以現行程式碼為準（`i18n_detector.py:667-673`）：

| 層 | 策略 | resolved_by | 可信度權重 |
| :---: | :--- | :--- | :---: |
| 1 | 使用者歷史偏好（曾手動選過的語系） | `EXPLICIT_HISTORY` | 1.00 |
| 2 | 系統語言精確匹配 | `OS_LANGS_EXACT`／`OS_LANGS_NEUTRAL_ZH` | 0.85／0.80 |
| 3 | 時區消歧 | `TIMEZONE_CROSS` | 0.80 |
| 4 | 系統語言模糊匹配（截斷區域碼） | `OS_LANGS_FUZZY` | 0.65 |
| 5 | GeoIP（線上 API 與離線 MaxMind 雙驗證，含 VPN 交叉檢查） | `GEOIP_VERIFIED`／`GEOIP_SINGLE_SOURCE` | 0.95／0.85 |
| 6 | 預設兜底 | — | 低 |

**IP 鎖定模式**為**選用功能，預設關閉**。由使用者手動開啟後，略過上述六層，只依公網 IP 地理位置決定音軌。現行程式預設為開啟（`player_app.py:154`），與規格不符，登記為 DEF-005。交接文件中「不使用 IP/GeoIP」的描述已過時，以本節為準。

### 1.3 數學模型與指標定義

**(1) 單幀失真與 PSNR**（Y 通道，W×H 像素，第 i 幀）

$$MSE_i = \frac{1}{WH}\sum_{x,y}\left(Y'_i(x,y) - Y_i(x,y)\right)^2,\qquad PSNR_i = 10\log_{10}\frac{255^2}{MSE_i}$$

**(2) 全片 PSNR：一律採 MSE-first**（N 幀）

$$PSNR_{video} = 10\log_{10}\frac{255^2}{\frac{1}{N}\sum_{i=1}^{N} MSE_i}$$

報告時須同時註明 N 的範圍：「全片」或「僅嵌入幀」。

**(3) 已廢止算法（僅作對照，不得作為驗收數字）**：`stego_bench.py` 取 5 幀（索引 0, ⌊N/5⌋, …），MSE = 0 時記為 100 dB，再對 dB 取算術平均。此算法會系統性高估 PSNR。

**(4) 離散擴散失真模型** ✅（P3-7、P3-8，`src/test/video/images/distortion_model_log.txt`）

由 `pee_stego.coltuc_embed_core_numba`（`pee_stego.py:421-450`）推導，並以 `verify_distortion_model.py` 逐區塊獨立驗證：
- 預測誤差 p = x − (n + w − nw)。可擴張區塊（|p| ≤ 1）嵌入 1 bit b：P = 2p + b，修改量 d = P − p = p + b ∈ {−1, 0, 1, 2}；平移區塊（|p| > 1）：d = ±2。
- d 分散到 2×2 區塊：u = (⌊d/4⌋, ⌊(d+1)/4⌋, ⌊(d+2)/4⌋, ⌊(d+3)/4⌋)。因 |d| ≤ 2，**區塊平方誤差 Σuᵢ² = |d|**（非連續理論的 d²/4），且每像素 |Δ| ≤ 1。
- b 均勻隨機時，期望 |d|：p = 0 → 0.5；**p = +1 → 1.5**；p = −1 → 0.5；平移 → 2。
- **每嵌入 1 bit 的期望失真（一般式）**：D_exp = 0.5·q₀ + 1.5·q₊ + 0.5·q₋，其中 q₀、q₊、q₋ 為可擴張區塊中 p = 0、+1、−1 的比例。
- **對稱近似**：當 q₊ = q₋（p = ±1 出現次數相等；指次數對稱，不是失真對稱），化簡為 **D_exp = 1 − 0.5·q₀**。
- **單幀 MSE** = (N_exp·D_exp + 2·N_shift + SSE_保留列) ÷ (W·H)。平移區塊不載資料卻貢獻失真。

**實測（9 個樣本：Pixel cover 第 0/144/288/432/576 幀、cat.jpg、DE.jpg、PEE Stego.jpg、SEM_0420.JPG，隨機位元 seed 20261027，嵌滿單幀）**：
| 項目 | 結果 |
| :--- | :--- |
| Σuᵢ² = \|d\|、u 分配式、max\|Δ\| ≤ 1 | 6,632,602 個處理區塊，**0 個不符** |
| SSE 恆等式（實測 = Σ\|d\| + 保留列 LSB） | 9/9 逐位元相等 |
| p = ±1 次數對稱差 \|q₊ − q₋\| ÷ (q₊ + q₋) | 0.048% ～ 0.672%（**並非全部 < 0.2%**：cat 0.36%、PEE Stego 0.49%、frame 576 0.45%、SEM 0.67%） |
| D_exp 一般式 vs 實測 | 誤差 −0.51% ～ +0.33% |
| D_exp = 1 − 0.5·q₀ vs 實測 | 誤差 −0.67% ～ +0.27% |
| 由模型預測的單幀 PSNR vs 實測 | 差距 ≤ 0.01 dB（一般式 ≤ 0.0097 dB；對稱近似 ≤ 0.0094 dB） |
| 平移區塊佔總 SSE 的比例 | 7.2% ～ 76.6%（紋理越多越高；cat 64%、DE 77%） |

**結論**：Σuᵢ² = \|d\| 為恆等式，實測無例外；D_exp = 1 − 0.5·q₀ 在 9 個樣本上誤差 < 0.7%，但成立的前提是 q₊ ≈ q₋，論文應同時寫出一般式。交接資訊中「對稱差 < 0.2%」只對部分樣本成立，須更正為「< 0.7%（本實測範圍）」。另外，高紋理影像的失真有一半以上來自平移區塊，討論 Coltuc 的低失真優勢時須一併說明。

**(5) 嵌入率**：bpp = payload 位元數 ÷（嵌入幀數 × W × H）；另報全片 bpp = payload 位元數 ÷（總幀數 × W × H）。負載比例 α_video = 嵌入幀數 ÷ 總幀數。

**(6) 檔案膨脹** ⏳：須分兩段報告，不得合併成單一百分比：
- 第一段：原始來源（可能為有損，如 AV1/VP9）→ 無損 HEVC 基準檔（未嵌入）
- 第二段：無損 HEVC 基準檔 → stego 檔（嵌入造成的增量）

**(7) 已知取捨（客觀描述）**：Coltuc 的單幀失真較低（|Δ| ≤ 1），但嵌入後的無損 HEVC 檔案膨脹，在高負載下可能大於 Checkerboard（歷史報告：+222.97% vs +148.69%，載體已遺失、無法重現）。**不得宣稱 Coltuc 在所有指標上單向全面優於 Checkerboard**；兩者的膨脹差異須以 P3-10 重新實測。

---

## 2. 測試範圍 (Scope)

### 2.1 包含項目 (In-Scope)

| 代號 | 模組 | 測試功能 |
| :--- | :--- | :--- |
| **MOD-ALG** | 演算法核心 | Y 通道位元級還原、像素變動 ≤ ±1、色度不變、payload 通道無損、失真模型、PSNR（MSE-first）、容量與 bpp |
| **MOD-PK** | StegoPacker | 多軌載入、容量不足攔截、MP3 frame 邊界位元組分塊、無損 HEVC 輸出、舊版分塊格式的向下相容 |
| **MOD-PL** | StegoPlayer | Manifest／Chunk0／Chunk1 串流擷取、Chunk0 開播延遲、切換連續性、影音同步、語系自動選軌、手動切軌、Seek、損毀或有損轉碼 stego 的平滑降級 |
| **MOD-DL** | MultiAudioDownloader | URL 解析、多語系音軌清單、Node.js 偵測與降級、批次下載 |
| **MOD-PKG** | 發布包 | `build.bat` 產出 3 個 exe、乾淨環境（無 Python／無 FFmpeg）可執行 |

### 2.2 不包含項目 (Out-of-Scope)
1. **DRM 保護內容**的下載。
2. **有損通道強韌性**：stego 影片經有損轉碼（社群平台、YouTube、`mp4v` 等）後無法擷取，屬 RDH 本質，不列為缺陷；但播放器**必須平滑降級而不崩潰**（列入 TC-PL-05）。
3. **非 Windows 平台**的正式驗收；**Windows 10** 僅做參考測試，結果不阻擋發布（Q4-1）。
4. **`for_ip/` 雲端監控儀表板**本身。註：StegoPlayer 會讀取 `for_ip/` 下的 GeoIP 資料庫，此呼叫路徑屬 MOD-PL 範圍（見 DEF-003）。
5. **`.m4a` / `.aac` 音軌的分塊位元級還原**：目前仍走 ffmpeg 重新編碼路徑，為 DEF-001 的已知限制；本輪僅測可播放，不測位元級相等。

---

## 3. 測試策略與方法 (Test Strategy & Methodology)

### 3.1 功能性測試
- **正向流程**：多軌音訊 → StegoPacker 封裝 → StegoPlayer 擷取與播放 → 各軌 SHA-256 與原檔相等。
- **邊界與異常**：容量不足、極短影片、奇數／非 1080p 解析度、非標準 MP3、損毀檔、有損轉碼後的 stego。
- **向下相容**：以舊版（重新編碼分塊）封裝的 stego 須仍可擷取與播放。

### 3.2 非功能性測試

#### 3.2.1 可逆性與畫質（最高優先）
| 驗收項目 | 標準 | 性質 |
| :--- | :--- | :--- |
| Y 通道還原 | 每個嵌入幀還原後與原幀**位元級相同** | 硬性 |
| 像素變動 | 所有嵌入幀 max\|Y′ − Y\| ≤ 1 | 硬性 |
| 色度通道 | U/V 與原幀位元級相同 | 硬性 |
| 非嵌入幀 | 與原幀位元級相同 | 硬性 |
| payload 通道 | 擷取位元數與內容 == 嵌入位元數與內容 | 硬性 |
| 音軌（MP3） | 擷取檔 SHA-256 == 原檔 | 硬性（DEF-001 修正後） |
| 無損編碼 | stego 的 x265 SEI 含 `lossless` | 硬性 |
| PSNR 門檻 | MSE-first，依負載比例分級 | ⏳ 待 P3-6、P3-9 實測後訂定 |

PSNR 一律同時報告四個值（舊算法、全片 dB 平均、全片 MSE-first、僅嵌入幀 MSE-first），以免與 v1.0 數字混淆。

#### 3.2.2 效能
需區分兩種吞吐量，不得混用：
- **演算法吞吐量**：記憶體內 Numba 嵌入／擷取 FPS。
- **管線吞吐量**：含 FFmpeg 解碼、Y 通道還原、zlib 解壓與檔案寫出的端到端 FPS。

| 項目 | 目前實測 | 門檻 |
| :--- | :--- | :--- |
| 管線封裝（720 幀 1080p） | 205.5 s（約 3.5 FPS，`pixel_jimmy/e2e_log.txt`，01:00 左右）；37.5 s（約 19 FPS，`py311_rerun/e2e_log.txt`，09:18） | ⏳ |
| 管線擷取至第 179 幀（腳本環境） | 27.4 s（約 6.5 FPS）；4.7 s（約 38 FPS）；同上兩份 log | ⏳ |
| GUI 內擷取 | 慢：載入至第 179 幀 50.1 s（約 3.6 FPS），主執行緒停滯最長 6.5 s（`pixel_jimmy/gui_probe/gui_probe_log.txt`）；快：6.4 s（約 28 FPS），最長停滯 0.45 s（`py310/gui_probe/gui_probe_log.txt`） | ❌ 見 DEF-002 |
| Chunk0 開播延遲 | 慢：載入後 20.8 s 收到 Chunk0，再 9.9 s 音訊才前進；快：載入後 2.5 s 收到，再 1.5 s 音訊才前進（同上兩份 log） | ❌ 見 DEF-002 |

**執行間變異（重大）**：同一機器、同一輸入、同一 commit，封裝耗時在 35.7～205.5 s、擷取在 4.7～27.4 s 之間，**相差約 6 倍**（`pixel_jimmy/e2e_log.txt`、`py311_rerun/e2e_log.txt`、`py310/e2e_log.txt`）。Python 3.11 在 09:18 重跑為 37.5 s，與 3.10 的 35.7 s 相近，確認差異來自機器狀態（電源模式、溫度或背景負載，⏳ 未查明），不是 Python 版本。因此：① 效能門檻須以多次執行的中位數判定（⏳ 次數待定），且量測前須固定電源模式（接上電源、最佳效能）並記錄於 log；② 單次效能數字不得用於驗收或論文。

**量測機器**：所有效能數字一律在主要測試機（i7-1260P，視為最低支援規格）上量測；效能門檻在此機器上通過即視為達標。VM 只做功能驗收，不報效能數字。

**分塊播放的必要條件**：在 `initial_sec` 秒內解出 Chunk1，或協議改為多段分塊；否則必然在切點暫停（DEF-002）。

#### 3.2.3 相容性與多國語系
- **一般播放器相容（Q4-6）**：stego 檔以 **Windows 11 內建「媒體播放器」**播放，須正常顯示畫面與載體原音、可拖曳進度、無花屏或崩潰。
  - **前置條件**：已安裝 Microsoft Store 的「HEVC 視訊擴充功能」。未安裝時無法播放不列為缺陷，但使用說明須註明此需求。
  - 其他播放器（VLC、瀏覽器等）不在本輪範圍。
- **語系自動選軌（依 1.2 六層規格）**：
  - **逐層命中案例**：每一層至少一個「上一層未命中、由本層決定」的案例，並驗證 `resolved_by` 與預期一致。例如：有歷史紀錄 → 第 1 層；無歷史、系統語言 ja-JP 且有 ja 音軌 → 第 2 層；系統語言 zh（無區域）、時區 Asia/Taipei → 第 3 層；系統語言 en-GB 只有 en 音軌 → 第 4 層；系統語言無對應音軌、線上 → 第 5 層；離線且無任何匹配 → 第 6 層。
  - **環境矩陣**：Locale × 時區（zh-TW/Asia/Taipei、en-US/America/New_York、ja-JP/Asia/Tokyo、de-DE/Europe/Berlin、zh-TW + UTC 不一致組）× 網路（線上、離線、VPN）。
  - **IP 鎖定模式**：預設必須為關閉（DEF-005）；手動開啟後只依 IP 決定；關閉後回到六層邏輯；設定須跨重啟保存（QSettings）。

#### 3.2.4 回歸測試
`src/test/verify/` 為回歸測試集。每次修改 `pee_stego.py`、`audio_chunker.py`、`player_app.py`、`i18n_detector.py` 後須重跑，並將新 log 與前次比對。DEF-003 為未被攔截的回歸，顯示目前 commit 前沒有自動測試（RSK-07）。

### 3.3 測試方式與工具

| 類型 | 方式 | 工具／腳本 |
| :--- | :--- | :--- |
| 演算法與畫質 | 自動化 | `verify_jimmy.py` |
| 音軌擷取與分塊 | 自動化 | `verify_audio.py`、`verify_chunks.py`、`verify_mp3_split.py`、`verify_chunk_boundary.py` |
| 端到端封裝 | 自動化 | `verify_e2e_pack.py` |
| GUI 播放時間線 | 半自動化 | `gui_handoff_probe.py`（取樣 20 ms、自動截圖） |
| 主觀聆聽、UI 操作 | 手動 | 人耳判斷斷音與音畫同步；不能由探針取代 |
| 打包驗收 | 手動 | 乾淨 Windows 11 VM（VirtualBox／VMware，快照還原）；Win10 22H2 VM 參考測試 |
| 失真模型 | 自動化 | `verify_distortion_model.py`（P3-7、P3-8） |
| 負載掃描與檔案膨脹 | 自動化 | `verify_load_sweep.py`（P3-6、P3-9；`--encode` 量測 P3-10；`--payload-kib` 做跨方法同 payload 比較） |
| 極端內容 | 自動化 | `verify_zero_capacity_frames.py`（TC-ALG-09） |
| 封裝邊界 | 自動化 | `verify_packer_edges.py`（TC-PK-04、05） |
| FFmpeg 來源 | 自動化 | `verify_ffmpeg_source.py`（TC-ENV-02；亦驗證 TC-ENV-01 的切換機制） |
| 彙總 | 自動化 | `summarize_sweep.py`（負載掃描 log → 表格） |
| 語系決策鏈 | 自動化 | `verify_i18n_layers.py`（TC-PL-06；重現 DEF-003） |
| 合成載體 | 自動化 | `gen_synthetic.py`（7 種圖樣，位元級可重現） |

自動化與手動的比例 ⏳ 待測試案例數量定案後計算（v1.0 的 65% / 35% 無依據，已刪除）。

### 3.4 測試案例清單（摘要）

完整前置條件、步驟、預期結果與證據見 `TEST_CASES_SPECIFICATION.md`。

| ID | 項目 | 狀態 | 證據 |
| :--- | :--- | :---: | :--- |
| TC-ALG-01 | Y 通道位元級還原 | ✅（1 支載體） | `pixel_jimmy/verify_log.txt`：179/179 |
| TC-ALG-02 | 像素變動 ≤ ±1 | ✅（1 支） | 同上：max\|Δ\| = 1 |
| TC-ALG-03 | 色度不變、非嵌入幀不變 | ✅（1 支） | 同上：0 幀不同 |
| TC-ALG-04 | payload 位元相等 | ✅（1 支） | 同上：80,725,184 / 80,725,184 |
| TC-ALG-05 | 無損編碼旗標 | ✅（1 支） | 同上：SEI 含 `lossless` |
| TC-ALG-06 | 離散擴散失真模型 | ✅（9 樣本） | `images/distortion_model_log.txt` |
| TC-ALG-07 | PSNR 對負載曲線 | ⏳ | P3-6、P3-9 |
| TC-ALG-08 | 檔案膨脹（兩段式，Coltuc vs Checkerboard） | ⏳ | P3-10 |
| TC-PK-01 | 端到端封裝 → 擷取，14 軌 SHA-256 相等 | ✅ | `pixel_jimmy/e2e_log.txt` |
| TC-PK-02 | MP3 位元組分塊（initial_sec 3.0 / 6.0） | ✅ | `pixel_jimmy/mp3_split_log.txt`：28/28 |
| TC-PK-03 | 舊分塊格式向下相容 | ✅ | 同上：14/14 |
| TC-PK-04 | 容量估計與容量不足攔截 | ❌ 部分 | DEF-007、DEF-008（`packer/packer_edges_log.txt`） |
| TC-ALG-09 | payload 跨越容量為 0 的幀（全黑／全白）仍可擷取 | ❌ | DEF-006（`synthetic/zero_cap_log.txt`） |
| TC-PK-05 | 非標準 MP3 分塊（6 種） | ✅ | `packer/packer_edges_log.txt` |
| TC-PL-01 | Chunk0 立即開播 | ❌ | DEF-002（收到 Chunk0 後 9.9 s 音訊才前進） |
| TC-PL-02 | 切點連續無斷音 | ❌ | DEF-002（跳過約 1.07 s） |
| TC-PL-03 | 影音同步 | ❌ | DEF-002（落後最多約 4.0 s） |
| TC-PL-04 | 切點靜音缺口 | ✅ | DEF-001 修正，`mp3_split_log.txt` |
| TC-PL-05 | 損毀／有損轉碼 stego 平滑降級 | ❌ 部分 | H.264 轉碼降級正常；chunk0 後才失敗則卡住（DEF-009） |
| TC-PL-06 | 語系自動選軌（六層逐層命中） | ❌ 部分 | 第 1–4、6 層 8/8 通過；本機時區判定失效（DEF-010）；`env/i18n_layers_log.txt` |
| TC-PL-08 | IP 鎖定模式（預設關閉、手動開關、跨重啟保存） | ❌ | DEF-003、DEF-005 |
| TC-PL-07 | 手動切軌、Seek | ⏳ | — |
| TC-DL-01～03 | URL 解析、多軌下載、無 Node.js 降級 | ⏳ | — |
| TC-CMP-01 | stego 檔以 Win11 媒體播放器播放（前置：HEVC 視訊擴充功能） | ⏳ | — |
| TC-ENV-01 | 以 `IMAGEIO_FFMPEG_EXE` 指定系統 FFmpeg，封裝→擷取回歸 | ⏳ | — |
| TC-ENV-02 | PATH 上有其他 ffmpeg 時，程式仍使用內附版本 | ✅ | `env/ffmpeg_source_log.txt` |
| TC-ENV-03 | Python 3.10 回歸 | ✅ | `pixel_jimmy/py310/`（與 3.11 除耗時外全同） |
| TC-PKG-01～02 | `build.bat`、乾淨 VM | ⏳ | — |

---

## 4. 測試標準 (Criteria)

### 4.1 進入標準 (Entry Criteria)
1. `src/test/verify/` 所有腳本與受測程式碼已 commit；重跑後 log 不帶 `uncommitted changes` 標記。
2. 每個測試載體都有 `SOURCES.txt`（來源、原始檔名、授權限制）與 SHA-256。
3. 正式載體集已建立（Q4-7）：Xiph derf 四支（crowd_run、park_joy、old_town_cross、sintel_trailer）與確定性合成影片，皆有 `SOURCES.txt` 與 SHA-256。
4. `build.bat` 可在測試機產出 3 個 exe。
5. 規格待確認項目已有結論（Q4-5 已於 2026-10-27 確認）。
6. `requirements.txt` 已全部鎖版並加入 PyInstaller（✅ 已完成，相依解析於 3.10／3.11 皆通過）；Python 3.10 與 3.11 兩個環境皆實際安裝並通過 `src/test/verify/` 回歸測試（✅ 2026-10-27，結果位元級一致）（Q4-3）。

### 4.2 退出／完成標準 (Exit Criteria)
1. **Blocker、Critical 缺陷：0 個 Open。**（目前 Open：DEF-006）
2. **Major 缺陷**：全部修正；未修正者須經 PM 書面核可並列入已知問題。**例外：DEF-002 為必修，不得以已知問題結案（Q6b）。** 目前 Open：DEF-002、DEF-003、DEF-005、DEF-009、DEF-010。
3. 3.2.1 所有「硬性」項目在**全部正式載體**上 100% 通過。
4. 3.4 所有測試案例皆已執行（無 ⏳）。
5. 文件與論文中引用的每一個數字，皆可對應到 commit 後產生的原始 log。
6. 交付物（第 9 章）齊全。

### 4.3 缺陷嚴重度定義
| 等級 | 定義 |
| :--- | :--- |
| Blocker | 崩潰、當機、無法啟動 |
| Critical | 可逆性失敗、payload 損毀、像素變動 > 1 |
| Major | 功能異常或品質缺陷，但核心流程可完成（例：DEF-001～003） |
| Minor | 顯示或非關鍵行為錯誤（例：DEF-004） |

---

## 5. 測試環境與工具 (Environment & Tools)

### 5.1 環境矩陣

| 項目 | 主要測試機（已實測） | 相容性環境 |
| :--- | :--- | :--- |
| 機器 | LAPTOP-BA0FPL1L | **乾淨 VM**（VirtualBox 或 VMware，全新 Windows 11 映像，未安裝 Python／FFmpeg；以快照反覆還原）；另設 Win10 22H2 VM 作參考測試 |
| 作業系統 | Windows 11 Home 10.0.26200（**必測**） | Win11（必測）；Win10 22H2（**參考測試**：失敗列為已知問題，不阻擋發布） |
| CPU | Intel Core i7-1260P（12 核 16 緒）——**最低支援規格**（Q4-2） | VM 依宿主機配置，不作效能量測 |
| RAM | 15.7 GB | VM：≥ 8 GB |
| GPU | Intel Iris Xe（內顯）。程式未使用 CUDA；GPU 僅負責影片解碼與顯示，不列為效能變因 | — |
| Python | 3.11.5（必測）；**3.10.11（必測）**：python.org NuGet 套件 `python.3.10.11.nupkg`（SHA-512 與 NuGet 目錄相符），免安裝解壓於 session 暫存區並建立 venv（⏳ 尚未建立持久位置） | 打包版不需 Python |
| 主要套件 | numpy 2.4.2、numba 0.65.0、opencv-python 4.13.0、PySide6 6.11.1、imageio-ffmpeg 0.6.0、yt-dlp 2026.03.17、requests 2.32.3、maxminddb 3.1.1、PyInstaller 6.21.0 | 與主要測試機相同（鎖版） |
| FFmpeg | ① imageio-ffmpeg 內附 ffmpeg 7.1（封裝、擷取、音訊分塊、下載合併）；② Qt Multimedia 後端 FFmpeg 7.1.3（播放）；③ **系統安裝的 FFmpeg**（Q4-4，版本 ⏳ 待選定） | 打包版內附 ①② |
| x265 | build 213（4.0+6），由 stego 檔 SEI 讀出 | — |
| Node.js | **v24.15.0（鎖定支援版本）**；另測「未安裝 Node.js」 | 未安裝 Node.js |

**版本政策（Q4-3）**：
- **Python**：3.10 與 3.11 皆為必測；從原始碼執行的回歸測試須在兩個版本各跑一次。README 的「3.10+」宣稱僅涵蓋這兩個版本。
- **鎖版（已完成，2026-10-27）**：`requirements.txt` 所有直接依賴皆以 `==` 鎖定，並新增 `pyinstaller==6.21.0` 與 `llvmlite==0.47.0`（numba 的 JIT 後端，版本影響編譯結果）。`requests` 由 `>=2.31.0` 改為 `==2.32.3`，`maxminddb` 由 `>=2.4.0` 改為 `==3.1.1`（皆為測試機實裝版本）。其餘間接依賴（共 23 個套件中的其他 13 個）未鎖定。
- **依 Python 版本分別鎖（Q4-3c）**：numpy 以環境標記分開鎖定：
  - `numpy==2.4.2; python_version >= "3.11"`
  - `numpy==2.2.6; python_version < "3.11"`
  - **查證（PyPI metadata）**：numpy 2.2.6（2025-05-17）`Requires-Python >=3.10`，有 `cp310-win_amd64` wheel，為 2.2 系列最後一版；2.3.0（2025-06-07）起改為 `>=3.11`。numba 0.65.0 要求 `numpy<2.5,>=1.22`；opencv-python 4.13.0.90 要求 `numpy>=2`（Python ≥ 3.9）。兩者皆與 2.2.6 相容。
  - **相依解析驗證**：以 `pip install --dry-run --only-binary=:all: --platform win_amd64` 分別對 Python 3.10、3.11 解析，兩者皆成功、各 23 個套件（3.10 → numpy 2.2.6；3.11 → numpy 2.4.2）。註：pip 的 `--python-version` 不會改變環境標記的判斷，3.10 解析是以標記展開後的等效清單模擬；標記本身已以 `packaging.markers` 驗證 3.10／3.11／3.12 的判斷正確。
  - 其他套件的 `Requires-Python` 皆涵蓋 3.10，使用同一組版本。
  - **3.10 實測（2026-10-27，commit `2bedda9`）**：於 Python 3.10.11 venv 以 `requirements.txt` 安裝（numpy 自動選 2.2.6），重跑全部 7 支驗證腳本與 GUI 探針，log 於 `src/test/video/pixel_jimmy/py310/`。與 3.11 的 log 逐行比對（去除 `#` 標頭）：`verify`、`audio`、`chunk`×2、`boundary`、`mp3_split` **全部相同**；`e2e` 僅耗時一行不同，**封裝出的 stego SHA-256 完全相同**（`0e0898b4…`）。結論：numpy 2.2.6／Python 3.10 與 numpy 2.4.2／Python 3.11 的輸出位元級一致。
  - **發現並修正**：Python 3.10.11 內附的 pip 23.0.1 以系統 locale（cp950）讀取 `requirements.txt`，原檔中的中文註解造成 `UnicodeDecodeError`，無法安裝；已將註解改為純 ASCII 並加註此限制（`4016071` 中的版本有此問題）。
  - **間接依賴漂移實例**：同一份 `requirements.txt`，3.10 venv 裝到 `pyinstaller-hooks-contrib 2026.9`、`certifi 2026.10.23`，3.11 測試機為 `2026.6`；間接依賴未鎖定的風險屬 RSK-06。
- ffmpeg／LAME 版本差異已實測會造成分塊位元組不同（RSK-06），因此 log 必須記錄 ffmpeg 版本。

**外部 FFmpeg 測試方式（Q4-4a）**：`pee_stego.py`、`audio_chunker.py`、`download_app.py` 皆經 `imageio_ffmpeg.get_ffmpeg_exe()` 取得 ffmpeg，**不讀取系統 PATH**；但該函式支援以環境變數 `IMAGEIO_FFMPEG_EXE` 指定外部執行檔。測試案例：
1. 設定 `IMAGEIO_FFMPEG_EXE` 指向系統 FFmpeg，重跑封裝 → 擷取回歸（`verify_e2e_pack.py`、`verify_jimmy.py`）；驗收標準同 3.2.1 硬性項目（位元級還原、MP3 SHA-256 相等）。
2. 僅把系統 FFmpeg 放在 PATH（不設環境變數）：確認程式仍使用內附版本（log 記錄的 ffmpeg 路徑）。
3. 若需求是「自動偵測並使用 PATH 上的 FFmpeg」，屬**新功能需求**，目前程式不支援，⏳ 待 PM 確認是否納入。

**Node.js 測試方式（Q4-4b）**：以 v24.15.0 為唯一支援版本測正常下載；另於未安裝 Node.js 的乾淨 VM 測降級：須出現友善提示、不崩潰，且不需 JS 執行環境的功能仍可使用（路徑：`pyinstaller_utils.get_node_path()`）。

### 5.2 測試資料（載體與音軌）

| 資料集 | 位置 | 用途 | 狀態 |
| :--- | :--- | :--- | :--- |
| Pixel 10「Switch like Jimmy Butler」：AV1 cover、14 軌 mp3、stego | `src/test/video/pixel_jimmy/` | 真實使用情境、端到端與 GUI 測試 | 可用；Google 廣告，**僅限內部測試，不得公開影格或音訊** |
| 「測試用黑白片段」12 支 | `src/test/video/drive_bw/` | 負面測試（有損轉碼 stego） | `mp4v` 有損、每支 5 幀、標頭損毀，**不可作為可逆性載體** |
| **正式載體集（Q4-7）**：Xiph derf 1080p 未壓縮 y4m — crowd_run（高紋理，500 幀）、park_joy（中高紋理，500 幀）、old_town_cross（平滑，500 幀）、sintel_trailer（CG，1253 幀），共 8,562,947,871 bytes | `src/test/video/xiph/`（`SOURCES.txt` 記錄大小、幀數、y4m 標頭、SHA-256 與出處） | P3-6、P3-9、P3-10 與論文數據 | 已下載並驗證（2026-10-27）。授權：SVT 三支為 **CC BY-NC-ND 4.0**（EBU，依 3GPP TR 26.955；EBU 條款 PDF 本身未取得）；sintel 為 **CC BY 3.0**（Blender Foundation） |
| **確定性合成影片**：flat128、hgrad、dgrad、shapes、noise、black、white，各 24 幀 1080p（`gen_synthetic.py`，兩次生成 SHA-256 相同） | `src/test/video/synthetic/`（`SOURCES.txt` 記錄指令與 SHA-256） | 控制組、RSK-01 極端內容、TC-ALG-09 | 已產生（腳本待 commit） |
| v1.0 的 `real_*.mp4` / `synthetic_*.mp4` | 遺失 | — | 不可重現，歷史數字作廢 |

**保存規則**：媒體檔一律不進 git（`.gitignore` 白名單只放行 `src/test/video/**/*.txt`）；repo 只保存 `SOURCES.txt`、SHA-256 與 log。

### 5.3 工具
- **驗證腳本**：`src/test/verify/`（共用標頭 `_common.py`）
- **缺陷追蹤**：`DEFECT_LOG.md` 為唯一正式紀錄（Q5b），與驗證腳本、log、程式碼一同版本控制；不同步至外部系統。每筆缺陷須含：嚴重度、狀態、模組與行號、發現版本、現象、根本原因（或初步分析）、證據 log、重現步驟、限制。
- **校驗**：Python `hashlib` SHA-256（由腳本自動記錄）

---

## 6. 資源與角色分工 (Resources & Roles)

人員指派由專題組之後填寫（Q5a）；指派欄保留空白（⏳）。

| 角色 | 職責 | 指派 |
| :--- | :--- | :--- |
| QA Lead | 維護本計畫、測試案例與缺陷紀錄；主持缺陷分級；產出結案報告 | ⏳ |
| 測試工程師 | 撰寫與執行 verify 腳本、GUI 手動測試、主觀聆聽 | ⏳ |
| 核心開發 | 修正 DEF-002、DEF-003；提供可建置版本 | ⏳（`git log` 主要提交者：zhanallen、Zong-You Chen） |
| 測試資料保管 | 提供素材原檔、生成腳本與授權說明，維護 `SOURCES.txt` | ⏳（現有素材由 zhanallen 提供） |
| PM／指導教授 | 核准本計畫、裁決規格變更、核可未修正的 Major 缺陷（DEF-002 除外） | 專題指導教授 |

---

## 7. 時程與進度估算 (Schedule & Estimation)

### 7.1 時程（Q6，2026-10-27 確認）

**目標交付日：2026-11-27**（結案報告完成）。**DEF-002 為發布前必修**；若 S3 修正與回歸無法在 11-20 完成，S3 延長，S4、S5 與交付日依實際天數順延，不以列為已知問題的方式結案。

| 階段 | 期間 | 主要工作 | 里程碑／出口 |
| :--- | :--- | :--- | :--- |
| S0 準備 | 2026-10-27 ～ 10-31 | commit 驗證腳本並重跑全部 log；requirements 鎖版；建立 Python 3.10 環境與乾淨 VM | 計畫書 v2.1 核准 |
| S1 載體與模型 | 11-02 ～ 11-06 | 下載正式載體、撰寫合成影片腳本；P3-7、P3-8 | 失真模型 log |
| S2 第一輪系統測試 | 11-09 ～ 11-13 | P3-6、P3-9、P3-10；TC-PK、TC-PL、TC-DL 全面執行 | 缺陷清單 |
| S3 修正與回歸 | 11-16 ～ 11-20（可延長） | 修正 DEF-002～005；全套 verify 回歸（Python 3.10、3.11 各一次） | 回歸 log；DEF-002 Closed |
| S4 發布驗收 | 11-23 ～ 11-25 | 乾淨環境 exe 驗收、一般播放器相容 | TC-PKG 通過 |
| S5 結案 | 11-26 ～ 11-27 | 測試總結報告、論文數據表 | 結案評審 |

### 7.2 估算依據
- 管線封裝實測 3.5～19 FPS（見 3.2.2 執行間變異）：以最慢情況估，一支 500 幀 1080p 序列封裝約 2.4 分鐘；4 支載體 × 3 個負載點 × 2 種演算法約 24 次封裝，純運算最多約 1 小時（不含擷取與 PSNR 計算）。
- DEF-002 牽涉分塊協議與播放器切換邏輯，修正工作量 ⏳ 待開發端評估；依 Q6b，S3 可延長、交付日順延。
- Python 3.10 與 3.11 雙環境使回歸測試時間約加倍。

---

## 8. 風險管理 (Risk Management)

| 編號 | 風險 | 嚴重度 | 機率 | 因應對策 |
| :--- | :--- | :---: | :---: | :--- |
| RSK-01 | 特定紋理或極端內容（全黑、全白、漸層）導致可逆性失效 | 極高 | **已發生** | DEF-006：payload 跨越全黑幀即無法擷取。合成載體集已納入全黑、全白、漸層（`gen_synthetic.py`）；所有載體跑 TC-ALG-01～05、09 |
| RSK-02 | yt-dlp 遭平台封鎖、簽章變更 | 高 | 高 | 下載測試與離線素材分離；記錄 yt-dlp 版本 |
| RSK-03 | 打包後缺少 DLL 或依賴 | 高 | 中 | 乾淨 VM 驗收（TC-PKG-02） |
| RSK-04 | 擷取速度不足，造成播放卡頓、不同步 | 高 | **已發生** | DEF-002；評估多段分塊、加長 `initial_sec` 或影片等待 Chunk0 |
| **RSK-05** | **測試資料遺失**，數字無法重現（v1.0 已發生） | 高 | 已發生 | 媒體不進 git，但必須有 `SOURCES.txt` 與 SHA-256；指定資料保管人；合成影片改用確定性腳本 |
| **RSK-06** | **依賴版本漂移**：ffmpeg／LAME 版本不同造成輸出位元組不同 | 中 | 已發生 | log 記錄所有版本；MP3 分塊改為位元組切割（DEF-001）以免受編碼器影響 |
| **RSK-07** | **回歸未被攔截**（`a5919e0` 帶出 DEF-003） | 高 | 已發生 | commit 前必跑 verify 腳本；之後評估 CI |
| **RSK-08** | **規格與實作不一致**：交接文件、程式預設值與確認後規格三者不同（Q4-5 已確認，DEF-005） | 中 | 已發生 | 規格以本文件 1.2 為準；每次規格變更須同步更新測試案例的預期結果 |
| **RSK-09** | **素材授權**：Pixel 廣告影片不可公開；SVT 序列為 CC BY-NC-ND 4.0（**禁止改作**），嵌入後的 stego 檔與其影格屬改作 | 中 | 中 | 論文只報告量測數字、只展示未修改的原始影格並註明來源；不公開 SVT 的 stego 檔或修改後影格；Sintel（CC BY 3.0）須附「© copyright Blender Foundation \| durian.blender.org」；廣告素材僅作內部測試 |

---

## 9. 測試可交付成果 (Deliverables)

| 交付物 | 位置 | 狀態 |
| :--- | :--- | :--- |
| 系統測試計畫書 | `SYSTEM_TEST_PLAN.md` | 本文件 v2.1（待核准） |
| 測試案例規格書 | `TEST_CASES_SPECIFICATION.md` | v1.0 草案（31 個案例：13 ✅、8 ❌、10 ⏳） |
| 自動化驗證腳本 | `src/test/verify/`（`_common.py` 與 7 支腳本） | 已 commit（`4016071`） |
| 原始 log 與資料來源 | `src/test/video/*/` 下的 `*.txt` 與 `SOURCES.txt` | `pixel_jimmy/` 8 份 log 已於 `4016071` 重跑、標頭乾淨（⏳ 尚未 commit）；`drive_bw/` 3 份 log 的產生腳本未入 repo，不可重現 |
| 缺陷紀錄 | `DEFECT_LOG.md`（DEF-001～004） | 進行中 |
| GUI 測試截圖 | `src/test/video/pixel_jimmy/gui_probe/`（不進 git） | 已產出 |
| 測試總結報告 | `TEST_SUMMARY_REPORT.md` | ⏳ S5 |

### 9.1 目前缺陷摘要

| ID | 標題 | 嚴重度 | 狀態 |
| :--- | :--- | :---: | :--- |
| DEF-001 | 分塊音軌合併後切點插入 31.6 ms 靜音，之後延遲 30.2 ms | Major | Fixed（`4016071` 重驗通過） |
| DEF-002 | 分塊串流播放無法維持影音同步 | Major | Open |
| DEF-003 | IP 鎖定策略建立 DetectionResult 時拋出 TypeError（`a5919e0` 回歸） | Major | Open |
| DEF-004 | chunk0 回報總時長為整首長度 | Minor | Open |
| DEF-005 | IP 鎖定模式預設為開啟，與規格「選用、預設關閉」不符 | Major | Open |
| DEF-006 | payload 跨越容量為 0 的幀時擷取失敗，整段音軌無法取回 | **Critical** | Open |
| DEF-007 | 容量不足時 GUI 錯誤處理引用未定義變數 `reply` | Minor | Open |
| DEF-008 | 容量不足要等全片編碼完才報錯，且留下無效 stego 檔 | Minor | Open |
| DEF-009 | 擷取在 chunk0 之後才失敗時，Player 停止播放、無法降級 | Major | Open |
| DEF-010 | 非英文 Windows 上時區無法判定國家，第 3 層與 VPN 交叉檢查失效 | Major | Open |

---

## 附錄 A：Phase 3 驗證項目狀態

| # | 項目 | 狀態 | 證據或缺口 |
| :--- | :--- | :---: | :--- |
| P3-1 | 像素變動 ≤ ±1 | ✅ | `pixel_jimmy/verify_log.txt` |
| P3-2 | 影像位元級還原 | ✅ | 同上 |
| P3-3 | payload 通道無損 | ✅ | 同上；`chunk_log_3s.txt` |
| P3-4 | 音軌與原檔位元級相同 | ✅（MP3） | `e2e_log.txt`；`.m4a`／`.aac` 未驗證 |
| P3-5 | 舊 PSNR 算法高估 | ✅ | `verify_log.txt`：同資料舊算法 82.05 dB，MSE-first 全片 61.01 dB |
| P3-6 | 單幀飽和 PSNR | 🟡 僅 1 支影片＋4 張圖 | 影片 54.77～56.71 dB、圖片 52.52～53.52 dB；需正式載體集 |
| P3-7 | Σuᵢ² = \|d\| | ✅ | `images/distortion_model_log.txt`：6,632,602 區塊 0 不符 |
| P3-8 | D_exp = 1 − 0.5·q₀、p = ±1 對稱 | ✅（附條件） | 同上：誤差 < 0.7%；對稱差 0.05–0.67%，非全部 < 0.2% |
| P3-9 | PSNR 對負載 | ⏳ | 待 `verify_load_sweep.py` |
| P3-10 | 兩段式檔案膨脹 | ⏳ | 待 `verify_filesize.py` |
| P3-11 | 舊報告 90.83／81.55／62.92 | 結案：無法重現 | 載體遺失；成因機制已由程式碼證實（`stego_bench.py:141`、`:479-486`） |
| P3-12 | 切點 30 ms 偏移 | ✅ 已查明並修正 | DEF-001 |

### A.1 第一組可追溯的真實影片實測（`pixel_jimmy/verify_log.txt`）
載體：Pixel 10 廣告，1920×1080，720 幀，23.98 fps；14 軌 mp3，payload 80,725,184 bits；嵌入 179 幀（α_video ≈ 24.9%）。

| 指標 | 數值 |
| :--- | :--- |
| 單幀 PSNR（嵌入幀） | 54.77 ～ 56.00 dB |
| MSE-first，僅嵌入幀（179） | **54.96 dB** |
| MSE-first，全片（720） | **61.01 dB** |
| 全片 dB 平均（MSE=0 記 100） | 88.80 dB |
| 舊 stego_bench 算法 | 82.05 dB |
| 嵌入率 | 0.2175 bpp（嵌入幀）；0.0541 bpp（全片） |

**限制**：單一載體，而且是有損 AV1 來源，不能代表一般化結論。log 已於 commit `4016071` 重跑，標頭乾淨，數值與 commit 前完全相同。

### A.2 合成載體負載掃描（`src/test/video/synthetic/load_sweep/summary.md`）
7 種合成圖樣 × 2 方法，負載 10/40/80/100% 與絕對 payload 256/1024 KiB；彙總表由 `summarize_sweep.py` 自各 log 產生。

| 觀察 | 數據 |
| :--- | :--- |
| 可逆性 | 所有可嵌入案例 restore_fail = 0、payload 位元相等 |
| 每幀容量 | Coltuc 約 0.249 bpp；Checkerboard 約 0.992–0.997 bpp（約 4 倍） |
| 零容量圖樣 | Coltuc：noise、black、white 全部幀容量 0；Checkerboard：black、white 為 0，noise 0.0102 bpp |
| 同 payload 1024 KiB 的全片 MSE-first PSNR | Coltuc 減 Checkerboard 為 −0.002～+0.89 dB（flat128 58.8726 vs 58.8746；hgrad 58.86 vs 57.97；dgrad 58.17 vs 57.92；shapes 58.22 vs 57.93） |
| 同 payload 1024 KiB 的「無損基準→stego」膨脹 | Coltuc 約為 Checkerboard 的 1.5～1.8 倍（hgrad +1201% vs +729%；shapes +1045% vs +678%） |
| 原因 | Coltuc 每幀容量低，同 payload 需分散到更多幀（α_video 0.708 vs 0.208） |

**限制**：合成影片僅 24 幀、內容極度規律（基準檔很小，膨脹百分比因此極大），只能當控制組；Checkerboard 的 skip map 不存於影像內，比較對其有利。正式結論以 Xiph 載體（A.3，⏳ 執行中）為準。

---

## 附錄 B：v1.0 作廢項目

| v1.0 內容 | 處理 | 原因 |
| :--- | :--- | :--- |
| 「無損」「資訊安全」「解密」用語 | 改寫 | 系統沒有金鑰；無損僅限 Y 通道與 payload 通道 |
| 單位元方均失真 ∼ p²/4 | 刪除 | 與離散模型 Σuᵢ² = \|d\| 不符 |
| PSNR 門檻 ≥ 90 dB（10%）、≥ 60 dB（80%） | 刪除 | 來自已廢止的算法，且載體已遺失 |
| SSIM ≥ 0.997 | 暫停 | 無可追溯 log；是否保留 SSIM 指標待討論 |
| 解密 ≥ 240 FPS（實測 245～2300） | 改寫 | 屬演算法吞吐量，不能代表管線；管線實測只有約 1～7 FPS |
| `libx265 crf 0` | 更正 | 程式實際使用 `lossless=1`（`pee_stego.py:620`） |
| Zhang-Zeng-Ou 2D HS | 移出範圍 | 非本套件主要路徑（`hevc_rdh_core` 模組不存在） |
| 本地語系 + IP 自動匹配 | 改寫 | 改為六層決策邏輯；IP 鎖定為選用功能、預設關閉（Q4-5） |
| RTX 40 / CUDA 環境 | 刪除 | 程式未使用 CUDA |
| 音軌 MD5 100% 吻合 | 保留並修正前提 | DEF-001 修正前不成立；修正後限 MP3 |
| 自動化 65% ／ 手動 35% | 刪除 | 無依據 |
| 2026-11-02 起的 4 週時程 | 改寫 | 改為 S0～S5，交付日 2026-11-27，DEF-002 必修（Q6） |

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
```

註：`verify_audio.py`、`verify_chunks.py`、`verify_chunk_boundary.py` 比對的是**舊版** stego（`chunked_stego.mp4`）的擷取結果，用以記錄 DEF-001 修正前的狀態。

---

## 附錄 D：待確認問題（Phase 4–6）

| ID | 問題 | 影響章節 |
| :--- | :--- | :--- |
| ~~Q4-1~~ | ✅ 已確認（2026-10-27）：只必測 Win11，Win10 22H2 為參考測試；乾淨環境用 VM（VirtualBox／VMware） | 2.2、3.3、5.1、TC-PKG |
| ~~Q4-2~~ | ✅ 已確認（2026-10-27）：現有 i7-1260P 筆電即最低支援規格，不另找低規機 | 3.2.2、5.1 |
| ~~Q4-3~~ | ✅ 已確認（2026-10-27）：Python 3.10 與 3.11 皆必測；全部依賴鎖版並加入 PyInstaller；numpy 依 Python 版本分別鎖（3.11：2.4.2，3.10：2.2.x） | 4.1、5.1 |
| ~~Q4-4~~ | ✅ 已確認（2026-10-27）：也測系統 FFmpeg（經 `IMAGEIO_FFMPEG_EXE`）；Node.js 鎖 v24.15.0，並測無 Node 降級。⏳ 系統 FFmpeg 版本待選定；「自動偵測 PATH」是否為新需求待 PM 確認 | 5.1、TC-ENV、TC-DL-03 |
| ~~Q4-5~~ | ✅ 已確認（2026-10-27）：六層決策邏輯（順序依程式碼）；IP 鎖定為選用、預設關閉 | 1.2、3.2.3、TC-PL-06/08、DEF-005 |
| ~~Q4-6~~ | ✅ 已確認（2026-10-27）：只測 Win11 媒體播放器；HEVC 視訊擴充功能列為前置條件 | 3.2.3、TC-CMP-01 |
| ~~Q4-7~~ | ✅ 已確認（2026-10-27）：Xiph 四支＋自製確定性合成影片；⏳ 待下載與撰寫生成腳本 | 4.1、5.2、P3-6/9/10 |
| ~~Q3-R2~~ | ✅ 已確認（2026-10-27）：以 `stego_bench.py` 的實作為準，輸出以相同 x265 lossless 參數編碼 | 1.2、TC-ALG-08 |
| Q5 | ✅ 缺陷追蹤以 `DEFECT_LOG.md` 為主（2026-10-27）；⏳ 人員指派之後填寫 | 5.3、6 |
| ~~Q6~~ | ✅ 已確認（2026-10-27）：交付日 2026-11-27；DEF-002 必修，必要時交付日順延 | 4.2、7 |

---
*本文件為 v2.1，經 PM 核准後生效。*
