# 系統測試總結報告 (Test Summary Report)
## 低變換失真預測誤差擴張多音軌播放與封裝套件

| 版本 | 日期 | 對應計畫書 | 狀態 |
| :--- | :--- | :--- | :--- |
| v0.2 | 2026-10-27 | `SYSTEM_TEST_PLAN.md` v3.0、`TEST_CASES_SPECIFICATION.md` v2.0、DE-SRS-001 v1.0 | **骨架**：期中狀態，標示 ⏳ 的段落待 S2～S5 完成後填寫 |

所有數字皆引用 repo 內的原始 log（路徑相對於 `src/test/video/`）。測試分支：`bugfix/def-001-007-qa-suite`（未 push）。

---

## 1. 摘要

| 項目 | 目前狀態 |
| :--- | :--- |
| 結案判定（PEP 6.2.4） | **未達成**：高優先 TC 44 項中 ✅ 16、❌ 6、◐ 8、⏳ 14；嚴重性 H 的 TBD 中 08 已修正待合併，02、07、11 未關閉；效能 TC 尚未在參考平台量測 |
| 核心可逆性宣稱 | 在已測載體上成立：Y 通道位元級還原、\|Δ\| ≤ 1、payload 位元相等、MP3 音軌 SHA-256 相等 |
| 主要風險 | 零容量幀（全黑、全白、高雜訊）出現在 payload 範圍內時，音軌無法取回（DEF-006）；鎖定的 yt-dlp 已無法下載多語音軌（DEF-011） |
| 播放體驗 | 分塊串流播放的開播、同步與切換皆不符預期（DEF-002、DEF-009） |

## 2. 測試範圍與環境

- 範圍：SRS 1.2（StegoPacker、StegoPlayer、核心函式庫）；下載器與 i18n 模組為範圍外（決議 K-1）。
- 正式驗收的參考平台為 SRS C-07（Win10、i7-1185G7、16 GB、Python 3.13），**尚未執行**；以下數據皆來自主要測試機 LAPTOP-BA0FPL1L（i7-1260P、15.7 GB、Win11 26200），效能數字只作參考。
- Python 3.11.5（numpy 2.4.2）與 3.10.11（numpy 2.2.6）；imageio-ffmpeg 內附 ffmpeg 7.1；x265 4.0+6。
- 載體：Pixel 10 廣告（內部測試）、Xiph derf 四支（SVT ×3 為 CC BY-NC-ND 4.0、Sintel 為 CC BY 3.0）、確定性合成影片 7 種、靜態圖片 4 張。

## 3. 測試案例執行統計

來源：`TEST_CASES_SPECIFICATION.md` v2.0 第 8 章（SRS 65 項需求，以腳本解析表格計數）。

| 狀態 | 全部 | 高優先 |
| :--- | ---: | ---: |
| ✅ 通過 | 18 | 16 |
| ❌ 不通過（含參考數據） | 11 | 6 |
| ◐ 部分／僅參考數據 | 11 | 8 |
| ⏳ 未執行 | 25 | 14 |
| **合計** | **65** | **44** |

另有 SRS 範圍外的觀察測試 7 項（i18n、下載器、環境），不計入通過率。

## 4. 缺陷統計

來源：`DEFECT_LOG.md`。

| 嚴重度 | 總數 | Open | Fixed |
| :--- | ---: | ---: | ---: |
| Blocker | 0 | 0 | 0 |
| Critical | 1 | 1（DEF-006） | 0 |
| Major | 7 | 6（DEF-002、003、005、009、010、011） | 1（DEF-001） |
| Minor | 4 | 3（DEF-004、008、012） | 1（DEF-007） |
| **合計** | **12** | **10** | **2** |

依主要影響模組（DEF-004、006 跨模組，各歸入一類）：MOD-ALG／PK 4（DEF-001、006、007、008）；MOD-PL 6（DEF-002、003、004、005、009、010）；MOD-DL 2（DEF-011、012）。
回歸缺陷：DEF-003 由 `a5919e0` 引入，顯示 commit 前缺少自動測試（RSK-07）。

## 5. 主要量測結果

### 5.1 可逆性與畫質（Pixel 載體，`pixel_jimmy/verify_log.txt`）
| 指標 | 數值 |
| :--- | :--- |
| 嵌入幀還原 | 179/179 位元級相同；色度 0 幀不同；非嵌入幀 0 幀不同 |
| max\|Δ\| | 1 |
| 單幀 PSNR（嵌入幀） | 54.77～56.00 dB |
| MSE-first PSNR | 全片 61.01 dB；僅嵌入幀 54.96 dB |
| 舊 stego_bench 算法 | 82.05 dB（同資料，高估約 21 dB） |
| Python 3.10 vs 3.11 | log 除耗時外逐行相同；stego SHA-256 相同（`pixel_jimmy/py310/`） |

### 5.2 離散失真模型（`images/distortion_model_log.txt`，9 樣本）
- Σuᵢ² = \|d\|：6,632,602 個區塊 0 不符。
- D_exp = 1 − 0.5·q₀ 誤差 < 0.7%；模型預測單幀 PSNR 與實測差 ≤ 0.01 dB。
- p = ±1 次數對稱差 0.05%～0.67%（交接資訊的 < 0.2% 不全成立）。
- 平移區塊佔總失真 7%～77%。

### 5.3 負載掃描與檔案膨脹
- 合成控制組（`synthetic/load_sweep/summary.md`）：同 payload 1024 KiB 時，Coltuc 與 Checkerboard 的全片 PSNR 差 −0.002～+0.89 dB，Coltuc 檔案膨脹為 Checkerboard 的 1.5～1.8 倍。
- **Xiph 正式載體**（`xiph/load_sweep/summary.md`，commit `047637d`，詳見 STP 附錄 A.3）：
  - Coltuc 24/24 案例可逆。
  - 自然場景（SVT ×3）Coltuc 容量 0.044～0.049 bpp，**不符合 REQ-PRF-005（≥ 0.15）**；CG（sintel）0.2234 bpp。
  - sintel 滿載（0.2234 bpp）時嵌入幀 PSNR 55.51 dB（REQ-PRF-001 ≥ 55），但「無損基準→stego」膨脹 +35.88%，**不符合 REQ-PRF-004（≤ 3%）**。
  - 同 payload 4096 KiB：全片 PSNR Coltuc 與 Checkerboard 互有高低（−1.15～+0.77 dB），檔案膨脹 4/4 為 Coltuc 較大。

### 5.4 播放行為（`pixel_jimmy/gui_probe/`、`pixel_jimmy/py310/gui_probe/`、`player_fallback/`）
- 機器狀態慢時：載入後 20.8 s 才收到 chunk0、影片暫停 16.3 s、切換跳過約 1.07 s 音訊。
- 機器狀態快時：不暫停，但開播延遲 1.5 s、切換仍跳過約 0.65 s。
- 有損轉碼 stego 降級正常；chunk0 之後才失敗則播放卡住。

### 5.5 效能變異
同一機器、同一輸入，封裝 35.7～205.5 s、擷取 4.7～27.4 s（約 6 倍）；效能數字須取多次執行中位數並固定電源模式。

## 6. 未執行項目與原因

| 類別 | 原因 | 後續 |
| :--- | :--- | :--- |
| PCK GUI 案例（001、003～005、007、010～012） | 需人工操作 | `MANUAL_TEST_CHECKLIST.md`；PEP WBS 2.3 |
| PLY 播放控制、清單、暫存清理（003、004、009～013、015） | 需人工操作 | M-03 |
| PRF-002（SSIM） | 腳本尚未計算 SSIM | 待加入 |
| PRF-006～010 正式判定 | 需參考平台 | 11/16～11/29 |
| POR-001、AVL-001 | 需乾淨 VM、離線環境 | M-07 |
| OTH-001、002；ALG-009；SEC-001；MNT-001 | 尚未執行（檢查或小型測試） | 11/09 前可完成 |

## 7. 結案判定與建議 ⏳

（S5 填寫）目前建議：
1. 優先修正 DEF-006（Critical），並以 `verify_zero_capacity_frames.py` 驗收。
2. DEF-002 為必修（Q6b），修正後須在快、慢兩種機器狀態下以 `gui_handoff_probe.py` 與人耳（M-01）驗收。
3. DEF-007（TBD-08）已修正並驗證，待 PR 合併；DEF-003、DEF-005 屬 SRS 範圍外，依決議 K-1 暫緩。
4. 論文中的 PSNR 與檔案膨脹數字一律採用 Xiph 正式載體與 MSE-first 算法；不得引用 v1.0 或舊報告數字。

## 附錄：交付物清單
`SYSTEM_TEST_PLAN.md`、`TEST_CASES_SPECIFICATION.md`、`MANUAL_TEST_CHECKLIST.md`、`DEFECT_LOG.md`、`src/test/verify/`（驗證腳本）、`src/test/video/*/`（原始 log 與 `SOURCES.txt`）、本報告。
