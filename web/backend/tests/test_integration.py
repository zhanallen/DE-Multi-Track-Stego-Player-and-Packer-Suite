"""End-to-end: real uvicorn + real stego_facade decoder + real SSE stream.

Uses $STEGO_SAMPLE when set, otherwise a freshly generated stego video
(see fixtures.py) — these tests must never be skipped.
"""

import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx
import imageio_ffmpeg

from web.backend.decode_worker import load_default_decoder
from web.backend.tests.sse_client import SseReader

TERMINAL_EVENTS = {"finished", "no_payload", "error"}
DECODE_TIMEOUT_SEC = 600  # first run on CI includes Numba JIT compilation


def _upload(server, video: Path) -> dict:
    with video.open("rb") as stream:
        response = httpx.post(server.url("/api/sessions"), files={"file": (video.name, stream, "video/mp4")}, timeout=60)
    assert response.status_code == 201, response.text
    return response.json()


def _start_decode(server, session_id: str) -> None:
    response = httpx.post(server.url(f"/api/sessions/{session_id}/decode"), timeout=30)
    assert response.status_code == 202, response.text


def _assert_audio_readable(audio_path: Path) -> None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        command = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)]
    else:  # imageio-ffmpeg ships ffmpeg only; decoding to null proves the same thing
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(audio_path), "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _assert_ordered(names: list[str], expected_order: list[str]) -> None:
    positions = [names.index(name) for name in expected_order]
    assert positions == sorted(positions), names


def test_full_streaming_decode_flow(start_live_server, stego_video, tmp_path):
    server = start_live_server()
    session = _upload(server, stego_video)
    session_id = session["session_id"]

    with SseReader(server.url(f"/api/sessions/{session_id}/events")) as reader:
        first_name, first_data = reader.next_event()
        assert first_name == "snapshot"
        assert first_data["state"] == "uploaded"
        assert first_data["chunks"] == {"0": {}, "full": {}}
        _start_decode(server, session_id)
        events = reader.collect_until(TERMINAL_EVENTS, timeout_sec=DECODE_TIMEOUT_SEC)

    names = [name for name, _data in events]
    assert names[-1] == "finished", events
    chunk_parts = [data["part"] for name, data in events if name == "chunk"]
    assert chunk_parts == ["chunk0", "full"]
    _assert_ordered(names, ["manifest", "chunk", "finished"])
    progress = [data for name, data in events if name == "progress"]
    assert len(progress) >= 1
    percents = [item["percent"] for item in progress]
    assert percents == sorted(percents)
    assert all(0 <= value <= 100 for value in percents)

    manifest = next(data for name, data in events if name == "manifest")
    assert {track["lang"] for track in manifest["tracks"]} == {"zh-TW", "en"}
    chunk0 = next(data for name, data in events if name == "chunk")
    track_url = server.url(chunk0["tracks"]["zh-TW"])
    response = httpx.get(track_url, timeout=30)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    downloaded = tmp_path / "chunk0.mp3"
    downloaded.write_bytes(response.content)
    _assert_audio_readable(downloaded)

    log_levels = {data["level"] for name, data in events if name == "log"}
    assert {"INFO", "PROCESS", "SUCCESS"} <= log_levels


def test_reconnect_receives_snapshot_with_missed_state(start_live_server, stego_video):
    """Disconnect mid-decode right after the manifest; chunk0 is produced while
    no client is listening, and the reconnect snapshot must contain both."""
    client_disconnected = threading.Event()
    chunk0_delivered = threading.Event()
    resume_after_chunk0 = threading.Event()
    real_decode = load_default_decoder()

    def gated_decode(video, output_dir, method, progress_callback, on_manifest_ready, on_chunk_ready):
        def manifest_then_wait(manifest):
            on_manifest_ready(manifest)
            client_disconnected.wait(60)

        def chunk_then_wait(chunk_idx, tracks, is_last):
            on_chunk_ready(chunk_idx, tracks, is_last)
            if chunk_idx == 0:
                chunk0_delivered.set()
                resume_after_chunk0.wait(60)

        return real_decode(video, output_dir, method=method, progress_callback=progress_callback,
                           on_manifest_ready=manifest_then_wait, on_chunk_ready=chunk_then_wait)

    server = start_live_server(load_decoder=lambda: gated_decode)
    session_id = _upload(server, stego_video)["session_id"]
    events_url = server.url(f"/api/sessions/{session_id}/events")
    try:
        first_reader = SseReader(events_url).__enter__()
        assert first_reader.next_event()[0] == "snapshot"
        _start_decode(server, session_id)
        first_reader.collect_until({"manifest"}, timeout_sec=DECODE_TIMEOUT_SEC)
        first_reader.close()  # browser drops the connection while decoding
        client_disconnected.set()
        assert chunk0_delivered.wait(DECODE_TIMEOUT_SEC)

        with SseReader(events_url) as second_reader:
            name, snapshot = second_reader.next_event()
            assert name == "snapshot"
            assert snapshot["state"] == "decoding"
            assert {track["lang"] for track in snapshot["manifest"]["tracks"]} == {"zh-TW", "en"}
            assert set(snapshot["chunks"]["0"]) == {"zh-TW", "en"}
            assert any("Chunk 0" in log["message"] for log in snapshot["logs"])
            resume_after_chunk0.set()
            events = second_reader.collect_until(TERMINAL_EVENTS, timeout_sec=DECODE_TIMEOUT_SEC)
        assert events[-1][0] == "finished"
        assert [data["part"] for name, data in events if name == "chunk"] == ["full"]
    finally:
        client_disconnected.set()
        resume_after_chunk0.set()


def test_plain_video_reports_no_payload(start_live_server, plain_video):
    server = start_live_server()
    session_id = _upload(server, plain_video)["session_id"]
    with SseReader(server.url(f"/api/sessions/{session_id}/events")) as reader:
        assert reader.next_event()[0] == "snapshot"
        _start_decode(server, session_id)
        events = reader.collect_until(TERMINAL_EVENTS, timeout_sec=DECODE_TIMEOUT_SEC)
    assert events[-1][0] == "no_payload"
    status = httpx.get(server.url(f"/api/sessions/{session_id}/status")).json()
    assert status["state"] == "no_payload"
    assert status["error"] is None


def _wait_until_finished(server, session_id: str) -> dict:
    deadline = time.monotonic() + DECODE_TIMEOUT_SEC
    while time.monotonic() < deadline:
        status = httpx.get(server.url(f"/api/sessions/{session_id}/status")).json()
        if status["state"] in TERMINAL_EVENTS:
            return status
        time.sleep(0.1)
    raise AssertionError("decode did not finish")


def test_security_works_offline_with_real_detector(start_live_server, stego_video, monkeypatch):
    from web.backend.config import ensure_src_on_path
    ensure_src_on_path()
    import i18n_detector

    def no_network(*_args, **_kwargs):
        raise OSError("simulated offline")

    monkeypatch.setattr(i18n_detector, "is_online", lambda *a, **k: False)
    if i18n_detector.requests is not None:
        monkeypatch.setattr(i18n_detector.requests, "get", no_network)

    server = start_live_server()
    session_id = _upload(server, stego_video)["session_id"]
    _start_decode(server, session_id)
    assert _wait_until_finished(server, session_id)["state"] == "finished"

    response = httpx.get(server.url(f"/api/sessions/{session_id}/security?ip_lock=true"),
                         headers={"Accept-Language": "zh-TW,en;q=0.5"}, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ip_lock"] is True
    assert body["recommended_track"] in {"zh-TW", "en"}
    assert body["decision_source"]
    assert isinstance(body["allowed_tracks"], list) and body["allowed_tracks"]
    assert body["file_md5"] is None or len(body["file_md5"]) == 32
