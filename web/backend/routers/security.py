"""GET /api/sessions/{id}/security — IP region decision for the security panel."""

from fastapi import APIRouter, Depends, Header, Query
from fastapi.concurrency import run_in_threadpool

from ..config import Settings
from ..dependencies import get_detector_loader, get_settings, get_store
from ..errors import ConflictError
from ..security_service import (
    build_security_report,
    detect_locale_safely,
    parse_accept_language,
    resolve_geoip_db_path,
)
from ..session_store import SessionStore
from ..urls import API_PREFIX

router = APIRouter(prefix=API_PREFIX, tags=["security"])


@router.get("/{session_id}/security")
async def get_security_report(
    session_id: str,
    ip_lock: bool = Query(True),
    accept_language: str | None = Header(None),
    store: SessionStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    load_detector=Depends(get_detector_loader),
) -> dict:
    session = store.get_session(session_id)
    available_tracks = session.get_available_langs()
    if available_tracks is None:
        raise ConflictError("manifest_not_ready", "尚未解出語系清冊 (manifest)，請稍後再查詢")
    # detect_best_locale may hit the network (GeoIP APIs), so keep it off the event loop.
    result = await run_in_threadpool(
        detect_locale_safely,
        load_detector,
        available_tracks,
        parse_accept_language(accept_language),
        resolve_geoip_db_path(settings.geoip_db_path),
        ip_lock,
    )
    return build_security_report(result, ip_lock, session.file_md5)
