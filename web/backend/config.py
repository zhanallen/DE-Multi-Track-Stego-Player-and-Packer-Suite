"""Runtime settings for the web backend.

Every value can be overridden by an environment variable so the lab Windows
machines can be tuned without editing code (see web/README.md).
"""

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

ALLOWED_VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv")
LOG_HISTORY_LIMIT = 200
PROGRESS_MIN_INTERVAL_SEC = 0.2  # at most 5 progress events per second
SSE_HEARTBEAT_SEC = 15.0
DELETE_RETRY_COUNT = 3
DELETE_RETRY_DELAY_SEC = 0.5
UPLOAD_COPY_BUFFER_BYTES = 1024 * 1024


def _read_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    return int(raw_value) if raw_value else default


def _default_temp_root() -> Path:
    override = os.environ.get("STEGO_WEB_TEMP_ROOT")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "stego_web"


def _default_geoip_db_path() -> Path:
    override = os.environ.get("STEGO_WEB_GEOIP_DB")
    if override:
        return Path(override)
    return REPO_ROOT / "for_ip" / "i18n_security" / "data" / "dbip-country-lite.mmdb"


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    temp_root: Path
    max_upload_bytes: int
    geoip_db_path: Path
    sse_heartbeat_sec: float = SSE_HEARTBEAT_SEC

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            host=os.environ.get("STEGO_WEB_HOST", "127.0.0.1"),
            port=_read_int("STEGO_WEB_PORT", 8765),
            temp_root=_default_temp_root(),
            max_upload_bytes=_read_int("STEGO_WEB_MAX_UPLOAD_MB", 2048) * 1024 * 1024,
            geoip_db_path=_default_geoip_db_path(),
        )


def ensure_src_on_path() -> None:
    """Make ``src/`` importable, mirroring how stego_facade.py extends sys.path."""
    src_text = str(SRC_DIR)
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
