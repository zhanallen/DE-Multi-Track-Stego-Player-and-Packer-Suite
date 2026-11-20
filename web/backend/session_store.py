"""Session model and the single-instance session registry.

A ``Session`` owns its state machine and broadcasts every change as an SSE
event while holding its lock, so a client that grabs a snapshot and subscribes
atomically can never miss or double-receive an event.
"""

import asyncio
import datetime
import logging
import re
import tempfile
import threading
import uuid
from collections import deque
from enum import Enum
from pathlib import Path

from .config import LOG_HISTORY_LIMIT
from .errors import ConflictError, SessionNotFoundError
from .events import EventBroadcaster, ServerEvent, Subscription
from .file_cleanup import DirectoryRemover
from .urls import build_track_url

logger = logging.getLogger(__name__)

SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
INPUT_FILE_STEM = "input"
TRACK_OUTPUT_DIR_NAME = "tracks"


class SessionState(str, Enum):
    UPLOADED = "uploaded"
    DECODING = "decoding"
    FINISHED = "finished"
    NO_PAYLOAD = "no_payload"
    ERROR = "error"


class TrackPart(str, Enum):
    CHUNK0 = "chunk0"
    FULL = "full"

    @property
    def snapshot_key(self) -> str:
        return "0" if self is TrackPart.CHUNK0 else "full"


class LogLevel(str, Enum):
    INFO = "INFO"
    PROCESS = "PROCESS"
    METADATA = "METADATA"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


class Session:
    def __init__(self, session_id: str, filename: str, directory: Path, video_suffix: str):
        self.session_id = session_id
        self.filename = filename
        self.directory = directory
        self.video_path = directory / f"{INPUT_FILE_STEM}{video_suffix}"
        self.output_dir = directory / TRACK_OUTPUT_DIR_NAME
        self.size_bytes = 0
        self._lock = threading.RLock()
        self._broadcaster = EventBroadcaster()
        self._state = SessionState.UPLOADED
        self._file_md5: str | None = None
        self._progress: dict | None = None
        self._manifest: dict | None = None
        self._track_paths: dict[TrackPart, dict[str, Path]] = {part: {} for part in TrackPart}
        self._logs: deque[dict] = deque(maxlen=LOG_HISTORY_LIMIT)
        self._error: str | None = None
        self._elapsed_sec: float | None = None

    # ---- read side -------------------------------------------------------
    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    @property
    def file_md5(self) -> str | None:
        with self._lock:
            return self._file_md5

    def get_track_path(self, lang: str, part: TrackPart) -> Path | None:
        with self._lock:
            return self._track_paths[part].get(lang)

    def get_available_langs(self) -> list[str] | None:
        """Track languages known so far (manifest first, else decoded result)."""
        with self._lock:
            if self._manifest is not None:
                return [track["lang"] for track in self._manifest["tracks"]]
            full_langs = list(self._track_paths[TrackPart.FULL])
            return full_langs or None

    def build_snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state.value,
                "filename": self.filename,
                "file_md5": self._file_md5,
                "progress": self._progress,
                "manifest": self._manifest,
                "chunks": {part.snapshot_key: self._build_track_urls(part) for part in TrackPart},
                "logs": list(self._logs),
                "error": self._error,
                "elapsed_sec": self._elapsed_sec,
            }

    def open_subscription(self, loop: asyncio.AbstractEventLoop) -> tuple[ServerEvent, Subscription]:
        with self._lock:
            snapshot = ServerEvent("snapshot", self.build_snapshot())
            return snapshot, self._broadcaster.subscribe(loop)

    def close_subscription(self, subscription: Subscription) -> None:
        self._broadcaster.unsubscribe(subscription)

    # ---- write side (called from the decode / checksum threads) ----------
    def set_file_md5(self, file_md5: str) -> None:
        with self._lock:
            self._file_md5 = file_md5

    def begin_decoding(self) -> None:
        with self._lock:
            if self._state is not SessionState.UPLOADED:
                raise ConflictError("invalid_state", f"目前狀態為 {self._state.value}，無法開始解碼")
            self._state = SessionState.DECODING

    def append_log(self, level: LogLevel, message: str) -> None:
        entry = {"level": level.value, "message": message, "ts": _now_iso()}
        with self._lock:
            self._logs.append(entry)
            self._publish("log", entry)

    def publish_progress(self, progress: dict) -> None:
        with self._lock:
            self._progress = progress
            self._publish("progress", progress)

    def set_manifest(self, manifest: dict) -> None:
        with self._lock:
            self._manifest = manifest
            self._publish("manifest", manifest)

    def record_chunk(self, chunk_idx: int, is_last: bool, track_files: dict[str, str]) -> None:
        part = TrackPart.FULL if is_last else TrackPart.CHUNK0
        with self._lock:
            self._register_tracks(part, track_files)
            self._publish("chunk", {
                "chunk_idx": chunk_idx,
                "is_last": is_last,
                "part": part.value,
                "tracks": self._build_track_urls(part, only=track_files.keys()),
            })

    def finish(self, track_files: dict[str, str], elapsed_sec: float) -> None:
        with self._lock:
            # Legacy (non-chunked) payloads never fire on_chunk_ready, so the
            # final result is the only place their files get registered.
            missing = {lang: path for lang, path in track_files.items()
                       if lang not in self._track_paths[TrackPart.FULL]}
            self._register_tracks(TrackPart.FULL, missing)
            self._state = SessionState.FINISHED
            self._elapsed_sec = elapsed_sec
            self._publish("finished", {
                "tracks": self._build_track_urls(TrackPart.FULL),
                "elapsed_sec": elapsed_sec,
            })

    def mark_no_payload(self, message: str, elapsed_sec: float) -> None:
        with self._lock:
            self._state = SessionState.NO_PAYLOAD
            self._elapsed_sec = elapsed_sec
            self._publish("no_payload", {"message": message})

    def mark_error(self, message: str, elapsed_sec: float) -> None:
        with self._lock:
            self._state = SessionState.ERROR
            self._error = message
            self._elapsed_sec = elapsed_sec
            self._publish("error", {"message": message})

    # ---- internals -------------------------------------------------------
    def _publish(self, name: str, data: dict) -> None:
        self._broadcaster.publish(ServerEvent(name, data))

    def _register_tracks(self, part: TrackPart, track_files: dict[str, str]) -> None:
        output_root = self.output_dir.resolve()
        for lang, raw_path in track_files.items():
            path = Path(raw_path).resolve()
            if not path.is_relative_to(output_root):
                logger.warning("忽略暫存目錄外的音軌路徑：%s", path)
                continue
            self._track_paths[part][lang] = path

    def _build_track_urls(self, part: TrackPart, only=None) -> dict[str, str]:
        langs = self._track_paths[part].keys() if only is None else only
        return {lang: build_track_url(self.session_id, lang, part.value)
                for lang in langs if lang in self._track_paths[part]}


class SessionStore:
    """Holds at most one session at a time (demo scope, one Numba job)."""

    def __init__(self, temp_root: Path, remover: DirectoryRemover):
        self._temp_root = temp_root
        self._remover = remover
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create_session(self, filename: str, video_suffix: str) -> Session:
        with self._lock:
            if self._has_decoding_session():
                raise ConflictError("decoding_in_progress", "已有影片正在解碼，請等待完成後再上傳")
            stale_sessions = list(self._sessions.values())
            self._sessions.clear()
            session = self._new_session(filename, video_suffix)
            self._sessions[session.session_id] = session
        for stale in stale_sessions:
            self._remover.remove(stale.directory)
        return session

    def get_session(self, session_id: str) -> Session:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise SessionNotFoundError()
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError()
        return session

    def begin_decoding(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError()
            session.begin_decoding()
            return session

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id) if SESSION_ID_PATTERN.fullmatch(session_id) else None
            if session is None:
                raise SessionNotFoundError()
            if session.state is SessionState.DECODING:
                raise ConflictError("decoding_in_progress", "解碼進行中，無法刪除")
            del self._sessions[session_id]
        self._remover.remove(session.directory)

    def is_decoding(self) -> bool:
        with self._lock:
            return self._has_decoding_session()

    def remove_all(self) -> None:
        """Shutdown hook: drop every session directory plus earlier failures."""
        with self._lock:
            directories = [session.directory for session in self._sessions.values()]
            self._sessions.clear()
        for directory in directories:
            self._remover.remove(directory)
        self._remover.remove_pending()

    def _has_decoding_session(self) -> bool:
        return any(session.state is SessionState.DECODING for session in self._sessions.values())

    def _new_session(self, filename: str, video_suffix: str) -> Session:
        session_id = uuid.uuid4().hex
        self._temp_root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix=f"{session_id}_", dir=self._temp_root))
        session = Session(session_id, filename, directory, video_suffix)
        session.output_dir.mkdir()
        return session
