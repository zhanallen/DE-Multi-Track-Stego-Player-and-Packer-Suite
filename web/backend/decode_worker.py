"""Background decode job: runs ``stego_facade.decode_video_multi`` in a thread
and translates its three streaming callbacks into session events."""

import logging
import threading
import time
from collections.abc import Callable

from .config import PROGRESS_MIN_INTERVAL_SEC, ensure_src_on_path
from .lang_map import get_display_name
from .session_store import LogLevel, Session

logger = logging.getLogger(__name__)

BYTES_PER_MB = 1048576
SCAN_LOG_EVERY_FRAMES = 30
DecodeFunction = Callable[..., dict]
Clock = Callable[[], float]


def load_default_decoder() -> DecodeFunction:
    # Imported lazily: stego_facade pulls in Numba/OpenCV, which tests may stub out.
    ensure_src_on_path()
    import stego_facade
    return stego_facade.decode_video_multi


def bits_to_megabytes(bits: int) -> float:
    return bits / 8 / BYTES_PER_MB


class ProgressReporter:
    """Turns raw progress callbacks into throttled ``progress`` payloads."""

    def __init__(self, min_interval_sec: float = PROGRESS_MIN_INTERVAL_SEC, clock: Clock = time.monotonic):
        self._min_interval_sec = min_interval_sec
        self._clock = clock
        self._last_frame: int | None = None
        self._last_time: float | None = None
        self._last_emit_time: float | None = None
        self._last_percent = 0
        self._fps = 0.0

    def build_payload(self, current_frame: int, total_frames: int, bit_idx: int, target_bits: int) -> dict | None:
        now = self._clock()
        self._update_fps(current_frame, now)
        if self._last_emit_time is not None and now - self._last_emit_time < self._min_interval_sec:
            return None
        self._last_emit_time = now
        # Clamped so the bar never moves backwards (e.g. when the frame-based
        # estimate switches to the bit-based one, or auto mode retries a pass).
        self._last_percent = max(self._last_percent, self._compute_percent(current_frame, total_frames, bit_idx, target_bits))
        return {
            "current_frame": current_frame,
            "total_frames": total_frames,
            "bit_idx": bit_idx,
            "target_bits": target_bits,
            "payload_mb": round(bits_to_megabytes(bit_idx), 4),
            "target_mb": round(bits_to_megabytes(target_bits), 4) if target_bits > 0 else None,
            "fps": self._fps,
            "percent": self._last_percent,
        }

    def _update_fps(self, current_frame: int, now: float) -> None:
        if self._last_frame is not None and self._last_time is not None:
            frame_delta = current_frame - self._last_frame
            time_delta = now - self._last_time
            if frame_delta > 0 and time_delta > 0:
                self._fps = round(frame_delta / time_delta, 1)
        self._last_frame = current_frame
        self._last_time = now

    @staticmethod
    def _compute_percent(current_frame: int, total_frames: int, bit_idx: int, target_bits: int) -> int:
        if target_bits > 0:
            ratio = bit_idx / target_bits
        elif total_frames > 0:
            ratio = current_frame / total_frames
        else:
            ratio = 0.0
        return int(min(max(ratio, 0.0), 1.0) * 100)


class DecodeJob:
    def __init__(
        self,
        session: Session,
        decode_function: DecodeFunction,
        progress_reporter: ProgressReporter | None = None,
        clock: Clock = time.monotonic,
    ):
        self._session = session
        self._decode_function = decode_function
        self._progress_reporter = progress_reporter or ProgressReporter()
        self._clock = clock
        self._started_at = 0.0
        self._has_manifest = False
        self._has_logged_header = False
        self._last_scan_log_frame = 0
        self._initial_sec = 0.0

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name=f"decode-{self._session.session_id[:8]}", daemon=True)
        thread.start()
        return thread

    def run(self) -> None:
        self._started_at = self._clock()
        self._log_start()
        try:
            result = self._decode_function(
                str(self._session.video_path),
                str(self._session.output_dir),
                method="auto",
                progress_callback=self._on_progress,
                on_manifest_ready=self._on_manifest_ready,
                on_chunk_ready=self._on_chunk_ready,
            )
        except Exception as error:  # the engine signals "no payload" by raising
            self._handle_failure(str(error))
            return
        if not result:
            self._handle_failure("解碼引擎未回傳任何音軌")
            return
        elapsed_sec = self._elapsed_sec()
        self._session.append_log(LogLevel.SUCCESS, f"✅ 解碼完成：全片 {len(result)} 組多語音軌皆已解密就緒（耗時 {elapsed_sec:.2f} 秒）。")
        self._session.finish(result, elapsed_sec)

    # ---- callbacks (run on the decoder thread) ---------------------------
    def _on_progress(self, current_frame: int, total_frames: int, bit_idx: int, target_bits: int) -> None:
        try:
            self._log_progress_milestones(current_frame, total_frames, bit_idx, target_bits)
            payload = self._progress_reporter.build_payload(current_frame, total_frames, bit_idx, target_bits)
            if payload is not None:
                self._session.publish_progress(payload)
        except Exception:
            # pee_stego does not guard progress_callback; never let UI plumbing abort a decode.
            logger.exception("progress callback failed")

    def _on_manifest_ready(self, manifest_info: dict) -> None:
        self._has_manifest = True
        self._initial_sec = float(manifest_info.get("initial_sec", 0.0))
        tracks = [
            {"lang": track["id"], "display_name": get_display_name(track["id"]), "ext": track.get("ext", "")}
            for track in manifest_info.get("tracks", [])
        ]
        self._session.append_log(
            LogLevel.SUCCESS,
            f"⚡ [串流解碼] 已即時解析出語系清冊 (Manifest)！共 {len(tracks)} 國語系（首塊切片長度: {self._initial_sec:.1f}s）",
        )
        self._session.set_manifest({"initial_sec": self._initial_sec, "tracks": tracks})

    def _on_chunk_ready(self, chunk_idx: int, tracks_dict: dict, is_last: bool) -> None:
        if is_last:
            message = "🎉 完整音訊串流解碼完畢！多語音軌無縫接續完成。"
        else:
            message = f"⚡ [串流解碼] 首塊音訊 (Chunk {chunk_idx}，前 {self._initial_sec:.1f} 秒) 解碼就緒！可立即開播。"
        self._session.append_log(LogLevel.SUCCESS, message)
        self._session.record_chunk(chunk_idx, is_last, tracks_dict)

    # ---- helpers ----------------------------------------------------------
    def _log_start(self) -> None:
        self._session.append_log(LogLevel.INFO, "初始化 DE 多軌藏密播放系統...")
        self._session.append_log(LogLevel.INFO, f"載入載體影片檔: {self._session.filename}")
        self._session.append_log(LogLevel.PROCESS, "啟動 FFmpeg YUV420p 原生像素讀取管線...")
        self._session.append_log(LogLevel.PROCESS, "載入解密引擎，開始解碼（自動偵測演算法）...")

    def _log_progress_milestones(self, current_frame: int, total_frames: int, bit_idx: int, target_bits: int) -> None:
        if not self._has_logged_header and target_bits > 0:
            self._has_logged_header = True
            target_bytes = target_bits // 8
            self._session.append_log(LogLevel.SUCCESS, "解析成功！已讀取 PEE 隱寫中繼資料標頭 (Metadata Header)")
            self._session.append_log(
                LogLevel.METADATA,
                f"偵測到壓縮載荷大小: {target_bytes:,} Bytes ({bits_to_megabytes(target_bits):.2f} MB) | 預期位元: {target_bits:,} bits",
            )
        if current_frame - self._last_scan_log_frame >= SCAN_LOG_EVERY_FRAMES:
            self._last_scan_log_frame = current_frame
            self._session.append_log(LogLevel.INFO, f"已掃描 {current_frame}/{total_frames} 幀 | 已提取 {bit_idx:,} bits")

    def _handle_failure(self, reason: str) -> None:
        elapsed_sec = self._elapsed_sec()
        if self._has_manifest:
            self._session.append_log(LogLevel.ERROR, f"解碼失敗：{reason}")
            self._session.mark_error(reason, elapsed_sec)
            return
        self._session.append_log(LogLevel.WARNING, f"影像解密提示/異常: {reason}")
        self._session.append_log(LogLevel.INFO, "影片未含多語隱寫音軌，切換為「原生載體音訊播放模式」。")
        self._session.mark_no_payload("影片沒有藏密音軌，請改播影片原始聲音", elapsed_sec)

    def _elapsed_sec(self) -> float:
        return round(self._clock() - self._started_at, 2)
