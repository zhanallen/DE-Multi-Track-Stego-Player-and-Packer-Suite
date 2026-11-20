# StegoPlayer Web 後端 API

把 Qt 播放器（`src/player_app.py`）的「串流解碼」與「IP 地區判定」包成 HTTP API，供瀏覽器前端使用：
上傳影片 → SSE 即時進度與 log → 首塊音訊（chunk0）先播 → 完整音軌（full）解完後無縫切換 → 查看安全資訊。

- 只在本機執行：`http://127.0.0.1:8765`（避開 for_ip 儀表板的 8000）
- **Windows 為主要平台**，macOS 為次要（開發／自測）
- 不修改 `src/` 任何檔案；解碼直接呼叫 `stego_facade.decode_video_multi(method="auto")`

---

## 1. 實驗室電腦安裝（Windows）

需求：Python 3.10 以上（CI 用 3.12）、Git。以下指令在 **repo 根目錄** 的「命令提示字元」執行：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt -r web\backend\requirements.txt
```

## 2. 啟動

| 平台 | 指令 |
|---|---|
| Windows | 雙擊 `web\run_web.bat`，或在任意資料夾執行 `web\run_web.bat` |
| macOS | `./web/run_web.sh` |
| 手動 | 在 repo 根目錄：`python -m uvicorn web.backend.main:app --host 127.0.0.1 --port 8765` |

`run_web.bat` 會先 `chcp 65001` 並設定 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`：既有 `pee_stego.py` 會 print emoji，cp950 主控台會拋 `UnicodeEncodeError`。腳本會自動使用 `.venv`（若存在）。

## 3. ⚠️ Demo 前必做：先完整解碼一次

`pee_stego.py` 的 Numba 函式第一次執行時要 JIT 編譯（數十秒）。**錄影前請先用同一台電腦完整解碼任一支藏密影片一次**，讓 Numba 在 `%TEMP%\numba_cache` 建好快取，之後解碼才會是正常速度。換電腦、升級 Python／Numba，或清掉暫存資料夾之後，都要重做一次。

## 4. 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `STEGO_WEB_HOST` | `127.0.0.1` | 監聽位址（啟動腳本使用） |
| `STEGO_WEB_PORT` | `8765` | 監聽埠（啟動腳本使用） |
| `STEGO_WEB_TEMP_ROOT` | `<系統暫存>/stego_web` | session 暫存根目錄 |
| `STEGO_WEB_MAX_UPLOAD_MB` | `2048` | 上傳大小上限（MB），超過回 413 |
| `STEGO_WEB_GEOIP_DB` | `for_ip/i18n_security/data/dbip-country-lite.mmdb` | 離線 GeoIP 資料庫；檔案不存在時傳 `None` |
| `STEGO_SAMPLE` | （無） | 測試用：指定一支藏密 mp4；未設定時測試會自動產生 |

本服務不需要任何 API key，所以沒有 `.env`。

---

## 5. API 一覽

錯誤格式統一為 `{ "error": { "code": string, "message": string } }`。`session_id` 是 uuid4 hex（32 字元），**後端只接受 session_id 與 lang，不接受客戶端傳入的檔案路徑**。

| Method | Path | 成功 | 主要錯誤 |
|---|---|---|---|
| GET | `/api/health` | 200 `{status:"ok", decoding:bool}` | |
| POST | `/api/sessions`（multipart `file`） | 201 `{session_id, filename, size_bytes, video_url}` | 415 副檔名非 .mp4/.mov/.mkv、409 有工作在解碼、413 太大 |
| POST | `/api/sessions/{id}/decode` | 202 `{state:"decoding"}` | 409 狀態不是 uploaded |
| GET | `/api/sessions/{id}/events` | SSE（見第 6 節） | 404 |
| GET | `/api/sessions/{id}/status` | 200，內容同 SSE `snapshot` 的 data | 404 |
| GET | `/api/sessions/{id}/video` | 200／206（支援 Range） | 404 |
| GET | `/api/sessions/{id}/tracks/{lang}/{part}` | 200／206，`part` ∈ `chunk0`、`full` | 404 尚未產生 |
| GET | `/api/sessions/{id}/security?ip_lock=true` | 200（見第 7 節） | 409 manifest 尚未解出 |
| DELETE | `/api/sessions/{id}` | 200 `{deleted:true}` | 409 解碼中 |

- 狀態機：`uploaded → decoding → (finished | no_payload | error)`
- 同一時間只會有一個 session：上傳新檔時，舊的閒置或已完成 session 會先被清除；有工作在解碼時回 409
- 音軌 Content-Type：`.mp3`→`audio/mpeg`、`.m4a/.aac`→`audio/mp4`、`.webm`→`audio/webm`、`.wav`→`audio/wav`
- `/api/pack` 預留給日後的網頁版封裝器（`routers/pack.py`），目前沒有 endpoint

## 6. SSE 事件（`/events`）

連線後第一個事件一定是 `snapshot`，之後是即時事件，每 15 秒送一次 `: heartbeat`。斷線不影響解碼，重連時由 `snapshot` 補齊狀態。終止事件送出後連線仍保持開著（避免 EventSource 不斷自動重連），前端收到 `finished`／`no_payload`／`error` 後請自行 `close()`。

| event | data |
|---|---|
| `snapshot` | `{state, filename, file_md5, progress, manifest, chunks:{"0":{lang:url},"full":{lang:url}}, logs[最近200筆], error, elapsed_sec}` |
| `progress` | `{current_frame, total_frames, bit_idx, target_bits, payload_mb, target_mb, fps, percent}`，每秒最多 5 次 |
| `log` | `{level, message, ts}`，level ∈ INFO／PROCESS／METADATA／SUCCESS／WARNING／ERROR |
| `manifest` | `{initial_sec, tracks:[{lang, display_name, ext}]}` |
| `chunk` | `{chunk_idx, is_last, part:"chunk0"|"full", tracks:{lang:url}}` |
| `finished` | `{tracks:{lang:url}, elapsed_sec}` |
| `no_payload` | `{message}`：影片沒有藏密音軌，前端改播影片原聲 |
| `error` | `{message}` |

前端串接建議：收到 `chunk(part=chunk0)` 就開始播；收到 `chunk(part=full)` 後，在相同播放時間點切到 full URL。

## 7. `/security` 回傳

```json
{ "ip_lock": true, "client_ip": "1.2.3.4", "proxy": {"enabled": false, "detail": "Direct Connection"},
  "country": "TW", "decision_source": "P0 IP_LOCK_ENFORCED", "trust_level": "🛡️ 頂級置信 (IP 區域強制鎖定)",
  "recommended_track": "zh-TW", "allowed_tracks": ["zh-TW"], "file_md5": "…" }
```

呼叫 `detect_best_locale(manifest 的 lang 清單, Accept-Language 解析結果, None, db_path, ip_lock_mode=ip_lock)`，在 threadpool 執行。任何例外都會回 `decision_source="THREAD_ERROR"` 並維持 200。授權結果只給前端顯示，後端下載音軌時**不會**阻擋。

---

## 8. 設計決策

| 決策 | 理由 |
|---|---|
| 單一 session、單一解碼工作 | demo 只需要一個；避免多個 Numba 工作互搶 CPU |
| 上傳檔存成 `input<副檔名>`，原檔名只用於顯示 | 避開 Windows 非法字元與中文路徑問題 |
| 只回傳解碼器登記過的檔案，`lang` 只當 dict key 查表 | 從根本上杜絕 `../` 路徑穿越；不在暫存目錄內的路徑一律忽略 |
| 刪除失敗重試 3 次（間隔 0.5 秒），還是失敗就等關機時再清 | Windows 上正在串流的檔案無法刪除；不能因此回 500 |
| 關機（lifespan shutdown）清掉所有 session 暫存目錄 | 不在 `%TEMP%` 留下大檔 |
| SSE：事件在 session lock 內發布，`snapshot` 與訂閱也在 lock 內一起完成 | 重連時不會漏掉事件，也不會重複收到 |
| thread → asyncio 用 `loop.call_soon_threadsafe` | 解碼執行緒不直接碰 event loop 的物件 |
| `percent` 只增不減 | 進度改用位元計算或 auto 模式重試時，進度條不會倒退 |
| 判定失敗時：還沒收到 manifest → `no_payload`；已收到 → `error` | 普通影片會在第 1 幀就拋例外，要跟「解到一半壞掉」區分開 |
| 沒有 manifest 的舊版（單體）藏密格式解完後，以結果登記成 `full` 音軌，`/security` 也用它當音軌清單 | 舊格式不會觸發 chunk callback |
| Range 交給 Starlette `FileResponse` 處理 | 內建 206／416，不重複造輪子 |
| 解碼器與 i18n 偵測函式都用依賴注入（`create_app(load_decoder=…, load_detector=…)`） | 測試可以替換；正式執行時才 lazy import Numba |

## 9. 已知限制

- 封裝器輸出的是 **HEVC lossless（hvc1）** mp4。Chrome／Edge 需要硬體 HEVC 解碼支援才能用 `<video>` 播，Firefox 不支援。前端需要準備 fallback（例如只播音軌，或另外轉一份 H.264 預覽）
- `auto` 模式遇到沒有藏密的影片時，`stego_facade` 會再嘗試一次 PEE，所以普通影片會被掃兩遍（`src/` 不可改，維持現狀）
- `for_ip/` 與 `hevc_rdh/` 被 `.gitignore` 排除。沒有 mmdb 時只能依賴線上 GeoIP，或退回預設判定

## 10. 測試

```bat
.venv\Scripts\python.exe -m pytest web\backend -v
```

- `tests/test_units.py`：進度計算、Accept-Language、刪除重試、失敗分類
- `tests/test_api.py`：HTTP 契約（415／409／413／206、路徑穿越、刪除、模擬 Windows 檔案鎖、關機清理、CORS）
- `tests/test_integration.py`：真的 uvicorn + 真的解碼引擎 + 真的 SSE（完整串流、斷線重連、no_payload、離線 security）
- 沒設定 `STEGO_SAMPLE` 時，`tests/fixtures.py` 會用 imageio-ffmpeg 產生 3 秒合成影片與 2 條正弦波音軌（`demo_audio_zh-TW.mp3`、`demo_audio_en.mp3`），再用 `encode_video_multi` 做出藏密影片，所以**不會 skip**
- CI：`.github/workflows/web-backend-test.yml` 在 push 到 `feature/**` 或對 main 發 PR、且 `web/**` 或 `src/**` 有變更時，於 windows-latest 與 macos-latest 上跑 pytest
