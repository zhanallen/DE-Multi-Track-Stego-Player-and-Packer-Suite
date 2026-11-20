"""IP-region / Zero-Trust report built on ``i18n_detector.detect_best_locale``.

Mirrors ``I18nDetectionWorker`` + ``on_i18n_detection_completed`` in the Qt
player. The report is informational only: tracks are never blocked server-side.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ensure_src_on_path

logger = logging.getLogger(__name__)

DetectFunction = Callable[..., Any]
THREAD_ERROR_SOURCE = "THREAD_ERROR"
FALLBACK_TRACK = "en-US"
UNKNOWN_PROXY_DETAIL = "Unknown"

# Copied from player_app.py on_i18n_detection_completed (trust_map).
TRUST_LEVELS = {
    "P0 IP_LOCK_ENFORCED": "🛡️ 頂級置信 (IP 區域強制鎖定)",
    "P1 EXPLICIT_HISTORY": "🟢 高置信度 (使用者偏好)",
    "P2a OS_UI_LANGS_EXACT": "🟢 高置信度 (系統原生)",
    "P4a TIMEZONE_CROSS": "🟢 高置信度 (時區比對)",
    "P2b OS_UI_LANGS_FUZZY": "🟡 中置信度 (系統模糊)",
    "P4c GEOIP_VERIFIED": "🟡 中置信度 (地理驗證)",
    "P4b LOCAL_DB_ONLY": "🟡 中置信度 (離線地理)",
    "P5 SYSTEM_DEFAULT": "🔴 低置信度 (保底選軌)",
    THREAD_ERROR_SOURCE: "❌ 執行緒異常",
}
DEFAULT_TRUST_LEVEL = "🟡 中置信度"


@dataclass
class FallbackDetection:
    """Stand-in for DetectionResult when detection itself blew up."""

    track_key: str
    source: str = THREAD_ERROR_SOURCE
    metadata: dict = field(default_factory=dict)


def load_default_detector() -> DetectFunction:
    ensure_src_on_path()
    from i18n_detector import detect_best_locale
    return detect_best_locale


def parse_accept_language(header_value: str | None) -> list[str]:
    """``"zh-TW,zh;q=0.9,en;q=0.8"`` -> ``["zh-TW", "zh", "en"]`` (by q, stable)."""
    weighted: list[tuple[float, int, str]] = []
    for position, item in enumerate((header_value or "").split(",")):
        tag, _, params = item.strip().partition(";")
        tag = tag.strip()
        if not tag or tag == "*":
            continue
        quality = _parse_quality(params)
        if quality > 0:
            weighted.append((-quality, position, tag))
    return [tag for _quality, _position, tag in sorted(weighted)]


def _parse_quality(params: str) -> float:
    for param in params.split(";"):
        key, _, value = param.strip().partition("=")
        if key.strip() == "q":
            try:
                return float(value)
            except ValueError:
                return 0.0
    return 1.0


def resolve_geoip_db_path(db_path: Path) -> str | None:
    return str(db_path) if db_path.is_file() else None


def detect_locale_safely(
    load_detector: Callable[[], DetectFunction],
    available_tracks: list[str],
    system_languages: list[str],
    db_path: str | None,
    ip_lock: bool,
) -> Any:
    """Never raises: any failure becomes a THREAD_ERROR result (no HTTP 500)."""
    try:
        detect_best_locale = load_detector()
        return detect_best_locale(available_tracks, system_languages, None, db_path, ip_lock_mode=ip_lock)
    except Exception as error:
        logger.warning("IP 地區判定失敗：%s", error)
        return FallbackDetection(track_key=available_tracks[0] if available_tracks else FALLBACK_TRACK)


def build_security_report(result: Any, ip_lock: bool, file_md5: str | None) -> dict:
    metadata = getattr(result, "metadata", None) or {}
    return {
        "ip_lock": ip_lock,
        "client_ip": metadata.get("ip"),
        "proxy": {
            "enabled": bool(metadata.get("proxy_detected", False)),
            "detail": metadata.get("details", UNKNOWN_PROXY_DETAIL),
        },
        "country": metadata.get("country"),
        "decision_source": result.source,
        "trust_level": TRUST_LEVELS.get(result.source, DEFAULT_TRUST_LEVEL),
        "recommended_track": result.track_key,
        "allowed_tracks": list(metadata.get("allowed_tracks") or [result.track_key]),
        "file_md5": file_md5,
    }
