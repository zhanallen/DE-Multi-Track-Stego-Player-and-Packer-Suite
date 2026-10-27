# 系統測試案例規格書 (Test Cases Specification)
## 低變換失真預測誤差擴張多音軌播放與封裝套件

| 版本 | 日期 | 對應計畫書 | 狀態 |
| :--- | :--- | :--- | :--- |
| v1.0 | 2026-10-27 | `SYSTEM_TEST_PLAN.md` v2.1 | 草案 |

**狀態**：✅ 通過　❌ 不通過（附缺陷編號）　⏳ 未執行
**證據規則**：狀態欄的每一筆結果都必須指向 repo 內的 log（路徑相對於 `src/test/video/`，除非另註）。log 標頭須記錄腳本、commit 與環境；`<D>` = `src/test/video/pixel_jimmy`。
**共通前置條件 (PRE-0)**：主要測試機（i7-1260P、Win11 26200、Python 3.11.5 或 3.10.11）；依 `requirements.txt` 安裝；載體媒體已依各 `SOURCES.txt` 取得且 SHA-256 相符。

---

## 1. MOD-ALG 演算法核心

| ID | 目的 | 前置條件 | 步驟 | 預期結果 | 方式／腳本 | 狀態與證據 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-ALG-01** | Y 通道位元級還原 | 有 cover 與對應 stego | 1. 逐幀解碼 cover 與 stego（yuv420p）<br>2. 對 stego 依 `decode_video_multi` 的停止條件呼叫 `coltuc_decode_frame` 還原<br>3. 與 cover 逐位元比對 | 每個嵌入幀還原後與 cover 完全相同 | 自動：`verify_jimmy.py` | ✅ `pixel_jimmy/verify_log.txt`（179/179）、`py310/verify_log.txt` |
| **TC-ALG-02** | 像素變動上限 | 同上 | 計算每個嵌入幀 max\|Y′−Y\| | ≤ 1 | 自動：`verify_jimmy.py`、`verify_distortion_model.py` | ✅ 同上；`images/distortion_model_log.txt`（9 樣本） |
| **TC-ALG-03** | 色度與非嵌入幀不變 | 同上 | 比對每幀 U/V；比對 payload 結束後的幀 | U/V 全同；非嵌入幀全同 | 自動：`verify_jimmy.py` | ✅ `pixel_jimmy/verify_log.txt`（0 幀不同） |
| **TC-ALG-04** | payload 通道無損 | 同上 | 累積擷取位元，與嵌入位元數及內容比對 | 位元數相等；分塊格式各 chunk 通過 zlib 檢查 | 自動：`verify_jimmy.py`、`verify_chunks.py` | ✅ `pixel_jimmy/verify_log.txt`、`chunk_log_3s.txt` |
| **TC-ALG-05** | 無損編碼旗標 | stego 檔 | 讀取 x265 SEI | 含 `lossless` | 自動：`verify_jimmy.py` | ✅ `pixel_jimmy/verify_log.txt` |
| **TC-ALG-06** | 離散失真模型（P3-7、P3-8） | 影片幀與圖片 | 1. 以 seed 20261027 隨機位元嵌滿單幀<br>2. 由原圖與嵌入圖逐區塊反推 u、d<br>3. 計算 q₀、q₊、q₋ 與模型預測 | Σuᵢ² = \|d\| 無例外；SSE 恆等式成立；D_exp 模型誤差 < 1% | 自動：`verify_distortion_model.py` | ✅ `images/distortion_model_log.txt`（6,632,602 區塊 0 不符；誤差 < 0.7%） |
| **TC-ALG-07** | PSNR 對負載（P3-6、P3-9） | 正式載體集 | 負載 10/40/80/100% 依幀序貪婪嵌入，計算四種 PSNR | 可逆性全通過；報告四種 PSNR；門檻 ⏳ 待實測後訂定 | 自動：`verify_load_sweep.py`、`summarize_sweep.py` | ⏳ 合成控制組已跑（`synthetic/load_sweep/summary.md`）；Xiph 執行中 |
| **TC-ALG-08** | 兩段式檔案膨脹（P3-10） | 同上 | `--encode`：未嵌入與嵌入後皆以 `ultrafast lossless=1` 編碼；`--payload-kib` 做同 payload 跨方法比較 | 報告「來源→基準」與「基準→stego」兩段；不宣稱單向優勢 | 自動：`verify_load_sweep.py --encode` | ⏳ 同上 |
| **TC-ALG-09** | payload 跨越零容量幀 | 合成 shapes、black | 組出 shapes×2 → black×2 → shapes×22；單體與分塊各封裝 1 軌 mp3 後擷取 | 擷取檔 SHA-256 與原檔相同 | 自動：`verify_zero_capacity_frames.py` | ❌ **DEF-006**（`synthetic/zero_cap_log.txt`） |

## 2. MOD-PK StegoPacker

| ID | 目的 | 前置條件 | 步驟 | 預期結果 | 方式／腳本 | 狀態與證據 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-PK-01** | 端到端封裝→擷取 | cover.webm、14 軌 mp3 | `encode_video_multi(initial_sec=3.0)` → `decode_video_multi` | 14/14 軌 SHA-256 相同；stego 檔 SHA-256 可重現 | 自動：`verify_e2e_pack.py` | ✅ `pixel_jimmy/e2e_log.txt`、`py310/e2e_log.txt`、`py311_rerun/e2e_log.txt` |
| **TC-PK-02** | MP3 frame 邊界位元組分塊 | 14 軌 mp3 | `initial_sec` 3.0、6.0 各切割與合併 | 位元組相等、合併 SHA-256 相等、chunk1 為 frame sync、chunk0 長度 ≥ initial_sec 且為 PCM 前綴 | 自動：`verify_mp3_split.py` | ✅ `pixel_jimmy/mp3_split_log.txt`（28/28） |
| **TC-PK-03** | 舊分塊格式向下相容 | 舊版 stego 擷取出的 chunk | 以 `concatenate_chunks` 合併舊格式 chunk | 走 ffmpeg 路徑，輸出與修正前相同 | 自動：`verify_mp3_split.py` | ✅ 同上（14/14） |
| **TC-PK-04** | 容量估計與容量不足攔截 | 短載體＋大 payload | 1. 比較 `estimate_capacity()` 與逐幀實際容量<br>2. 以 API 封裝超過容量的音軌<br>3. GUI 封裝超量音軌 | 估計值不高估；超量時在寫入前報錯、不留殘缺檔；GUI 顯示錯誤且不拋例外 | 自動：`verify_packer_edges.py`；GUI 手動 | ❌ 部分：估計值實測皆低估（−0.1%～−14.4%，GUI 偏安全）；API 超量時全片編碼後才報錯並留下 4,613,913 B 殘檔（**DEF-008**）；GUI 對話框後 NameError（**DEF-007**，程式碼審查）；`packer/packer_edges_log.txt` |
| **TC-PK-05** | 非標準 MP3 分塊 | MPEG-2、亂碼、截斷、WAV 改名、ID3v1 | 呼叫 `split_audio_into_chunks` 與 `concatenate_chunks` | 不拋例外；可解析者位元組切割、不可解析者退回 ffmpeg；chunk0 長度 ≥ initial_sec | 自動：`verify_packer_edges.py` | ✅ 6 種非標準 MP3 皆不拋例外：MPEG-2、中段亂碼、截斷、ID3v1 走位元組切割；切點前亂碼、WAV 改名退回 ffmpeg；`packer/packer_edges_log.txt`。執行中發現並修正 MPEG-2 的 chunk0 比 initial_sec 短 24 ms（`audio_chunker.mp3_split_offset` 餘量改為 1152 samples） |

## 3. MOD-PL StegoPlayer

| ID | 目的 | 前置條件 | 步驟 | 預期結果 | 方式／腳本 | 狀態與證據 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-PL-01** | Chunk0 立即開播 | `e2e_stego.mp4`（initial_sec 3.0） | 啟動 Player 載入；20 ms 取樣播放器狀態 | 收到 Chunk0 後音訊位置在 ⏳ ms 內開始前進；影片不得先於音訊播放 | 半自動：`gui_handoff_probe.py` | ❌ **DEF-002**（慢：9.9 s；快：1.5 s） |
| **TC-PL-02** | 切點連續 | 同上 | 觀察 chunk0 → 完整音軌切換 | 新播放器起點 = 舊播放器位置（±50 ms，⏳）；切換前後皆為 Playing | 半自動＋人耳 | ❌ **DEF-002**（跳過 0.65～1.07 s） |
| **TC-PL-03** | 影音同步 | 同上 | 全程記錄 audio − video | \|audio − video\| ≤ ⏳ ms；不得因等待 chunk 暫停影片 | 半自動 | ❌ **DEF-002**（最多落後 4.0 s；暫停 16.3 s） |
| **TC-PL-04** | 合併音軌無切點靜音 | 位元組分塊的 stego | 擷取完整音軌，與原檔比對 | SHA-256 相同（因此無靜音、無延遲） | 自動：`verify_e2e_pack.py` | ✅ DEF-001 修正；`pixel_jimmy/e2e_log.txt` |
| **TC-PL-05** | 損毀／有損轉碼 stego 平滑降級 | `drive_bw/` 的 `mp4v` stego；DEF-006 產生的 stego | 以 Player 載入 | 顯示友善訊息、播放載體原音、不崩潰 | 手動 | ❌ 部分：H.264 有損轉碼 stego 降級正常、影片播完 10,010 ms（`player_fallback/h264_lossy/`）；chunk0 之後才失敗的 stego 播放卡住（**DEF-009**，`player_fallback/zero_cap_clean/`）；載體原音是否出聲待人耳確認 |
| **TC-PL-06** | 語系六層逐層命中 | 多軌音軌清單；可注入系統語言、歷史、時區 | 呼叫 `detect_best_locale()`（與 Player 同入口），以替換 `get_local_country_by_timezone` 控制時區，逐層構造 8 個案例 | 每案例的 `resolved_by` 與選中音軌符合預期；本機真實時區可判定國家 | 自動：`verify_i18n_layers.py` | ❌ 部分：第 1–4、6 層 8/8 通過；第 5 層（GeoIP）未涵蓋；**本機真實時區判定為 None（DEF-010）**；`env/i18n_layers_log.txt` |
| **TC-PL-07** | 手動切軌、Seek | 同 TC-PL-01 | 播放中切換 3 種語系；拖曳到 10 s、25 s | 切換後 1 s 內出聲、與畫面同步；Seek 後音畫同步 | 手動 | ⏳ |
| **TC-PL-08** | IP 鎖定模式 | 清除 QSettings | 1. 首次啟動確認預設<br>2. 手動開啟 → 載入<br>3. 關閉 → 重啟 | 預設關閉；開啟時只依 IP；設定跨重啟保存；不拋例外 | 手動 | ❌ **DEF-005**（預設開啟）、**DEF-003**（TypeError） |

## 4. MOD-DL MultiAudioDownloader

| ID | 目的 | 前置條件 | 步驟 | 預期結果 | 方式／腳本 | 狀態與證據 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-DL-01** | URL 解析與音軌清單 | 網路；Node.js v24.15.0 | 輸入多語系影片 URL | 列出影片與全部語系音軌 | 手動 | ⏳ |
| **TC-DL-02** | 多軌下載 | 同上 | 勾選多語系下載 | 產生影片與各語系 mp3，檔名符合 `*_audio_<lang>.mp3` | 手動 | ⏳ |
| **TC-DL-03** | 無 Node.js 降級 | 乾淨 VM，未安裝 Node.js | 啟動並嘗試解析 | 友善提示、不崩潰 | 手動 | ⏳ |

## 5. 相容性、環境與發布

| ID | 目的 | 前置條件 | 步驟 | 預期結果 | 方式／腳本 | 狀態與證據 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-CMP-01** | 一般播放器相容 | Win11 媒體播放器；已安裝 HEVC 視訊擴充功能 | 開啟 stego 檔播放、拖曳進度 | 正常顯示與出聲，無花屏、不崩潰 | 手動 | ⏳ |
| **TC-ENV-01** | 外部 FFmpeg | 系統安裝 FFmpeg（版本 ⏳） | 設 `IMAGEIO_FFMPEG_EXE` 後重跑 `verify_e2e_pack.py`、`verify_jimmy.py` | 3.2.1 硬性項目全通過 | 自動 | ⏳ |
| **TC-ENV-02** | PATH 上的 ffmpeg 不被誤用 | PATH 最前置誘餌 ffmpeg.exe | 靜態掃描 + 子行程解析並實際分塊；另測 `IMAGEIO_FFMPEG_EXE` 切換 | 預設與 PATH 誘餌皆用內附版本；設環境變數時改用指定版本 | 自動：`verify_ffmpeg_source.py` | ✅ PATH 最前置誘餌 ffmpeg 時仍用內附版本；靜態掃描 0 處寫死 ffmpeg；`env/ffmpeg_source_log.txt` |
| **TC-ENV-03** | Python 3.10 回歸 | Python 3.10.11 venv | 依 `requirements.txt` 安裝後重跑全部驗證腳本 | 與 3.11 的 log 除耗時外逐行相同 | 自動 | ✅ `pixel_jimmy/py310/`（全部相同；stego SHA-256 相同） |
| **TC-PKG-01** | 打包 | `.venv` 已建立 | 執行 `build.bat` | `dist/` 產出 3 個 exe，無錯誤 | 手動 | ⏳ |
| **TC-PKG-02** | 乾淨環境可執行 | 乾淨 Win11 VM（無 Python、無 FFmpeg） | 複製 `dist/` 並啟動 3 個 exe，執行 TC-PK-01 的 GUI 流程 | 正常啟動與封裝／播放；無缺 DLL | 手動 | ⏳ |

---

## 6. 摘要

| 狀態 | 數量 | 案例 |
| :--- | ---: | :--- |
| ✅ 通過 | 13 | ALG-01、ALG-02、ALG-03、ALG-04、ALG-05、ALG-06、PK-01、PK-02、PK-03、PK-05、PL-04、ENV-02、ENV-03 |
| ❌ 不通過（含部分不通過） | 8 | ALG-09、PK-04、PL-01、PL-02、PL-03、PL-05、PL-06、PL-08 |
| ⏳ 未執行 | 10 | ALG-07、ALG-08、PL-07、DL-01、DL-02、DL-03、CMP-01、ENV-01、PKG-01、PKG-02 |

合計 31 個案例。註：✅ 中「1 支載體」者尚須在正式載體集（Xiph 與合成）上重驗後才算最終通過。
