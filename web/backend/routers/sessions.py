"""Session lifecycle endpoints: upload, decode, SSE, status, media, delete."""

import asyncio

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from ..checksum import start_md5_computation
from ..config import Settings
from ..decode_worker import DecodeJob
from ..dependencies import get_decoder_loader, get_settings, get_store
from ..errors import ResourceNotFoundError
from ..events import stream_sse
from ..media_types import get_audio_media_type, get_video_media_type
from ..session_store import SessionState, SessionStore, TrackPart
from ..upload_service import copy_upload, get_display_filename, get_video_suffix
from ..urls import API_PREFIX, build_video_url

router = APIRouter(prefix=API_PREFIX, tags=["sessions"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("", status_code=201)
async def create_session(
    file: UploadFile = File(...),
    store: SessionStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    filename = get_display_filename(file.filename)
    suffix = get_video_suffix(filename)
    session = store.create_session(filename, suffix)
    try:
        session.size_bytes = await run_in_threadpool(copy_upload, file.file, session.video_path, settings.max_upload_bytes)
    except Exception:
        store.delete_session(session.session_id)
        raise
    start_md5_computation(session)
    return {
        "session_id": session.session_id,
        "filename": session.filename,
        "size_bytes": session.size_bytes,
        "video_url": build_video_url(session.session_id),
    }


@router.post("/{session_id}/decode", status_code=202)
def start_decoding(
    session_id: str,
    store: SessionStore = Depends(get_store),
    load_decoder=Depends(get_decoder_loader),
) -> dict:
    store.get_session(session_id)  # 404 for malformed / unknown ids before state checks
    decode_function = load_decoder()
    session = store.begin_decoding(session_id)
    DecodeJob(session, decode_function).start()
    return {"state": SessionState.DECODING.value}


@router.get("/{session_id}/events")
async def stream_session_events(
    session_id: str,
    store: SessionStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    session = store.get_session(session_id)
    snapshot, subscription = session.open_subscription(asyncio.get_running_loop())

    async def generate_events():
        try:
            async for message in stream_sse(snapshot, subscription, settings.sse_heartbeat_sec):
                yield message
        finally:
            session.close_subscription(subscription)

    return StreamingResponse(generate_events(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/{session_id}/status")
def get_session_status(session_id: str, store: SessionStore = Depends(get_store)) -> dict:
    return store.get_session(session_id).build_snapshot()


@router.get("/{session_id}/video")
def get_session_video(session_id: str, store: SessionStore = Depends(get_store)) -> FileResponse:
    session = store.get_session(session_id)
    if not session.video_path.is_file():
        raise ResourceNotFoundError("影片檔不存在")
    return FileResponse(session.video_path, media_type=get_video_media_type(session.video_path))


@router.get("/{session_id}/tracks/{lang}/{part}")
def get_session_track(session_id: str, lang: str, part: str, store: SessionStore = Depends(get_store)) -> FileResponse:
    session = store.get_session(session_id)
    try:
        track_part = TrackPart(part)
    except ValueError:
        raise ResourceNotFoundError("part 只接受 chunk0 或 full") from None
    # Only paths the decoder registered are served; ``lang`` is a dict key, never a path.
    track_path = session.get_track_path(lang, track_part)
    if track_path is None or not track_path.is_file():
        raise ResourceNotFoundError("音軌尚未產生")
    return FileResponse(track_path, media_type=get_audio_media_type(track_path))


@router.delete("/{session_id}")
def delete_session(session_id: str, store: SessionStore = Depends(get_store)) -> dict:
    store.delete_session(session_id)
    return {"deleted": True}

