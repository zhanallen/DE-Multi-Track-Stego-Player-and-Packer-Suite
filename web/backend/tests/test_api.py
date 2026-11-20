"""HTTP contract tests with an injected (controllable) decoder."""

import hashlib
import shutil
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from web.backend.file_cleanup import DirectoryRemover
from web.backend.security_service import FallbackDetection

FAKE_VIDEO_BYTES = bytes(range(256)) * 64  # 16 KiB, enough for Range checks
STATE_WAIT_TIMEOUT_SEC = 10


class ControlledDecoder:
    """Stub of decode_video_multi that blocks until the test releases it."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, video_path, output_dir, method, progress_callback, on_manifest_ready, on_chunk_ready):
        self.started.set()
        self.release.wait(STATE_WAIT_TIMEOUT_SEC)
        output = Path(output_dir)
        on_manifest_ready({"initial_sec": 6.0, "tracks": [{"id": "en", "filename": "a_audio_en.mp3", "ext": ".mp3"}]})
        chunk0 = output / "en_chunk0.mp3"
        chunk0.write_bytes(b"ID3chunk0")
        on_chunk_ready(0, {"en": str(chunk0)}, False)
        progress_callback(10, 90, 500, 1000)
        full = output / "en.mp3"
        full.write_bytes(b"ID3full")
        on_chunk_ready(1, {"en": str(full)}, True)
        return {"en": str(full)}


def _upload(client, name="demo.mp4", content=FAKE_VIDEO_BYTES):
    return client.post("/api/sessions", files={"file": (name, content, "application/octet-stream")})


def _wait_for_state(client, session_id, expected_state):
    deadline = time.monotonic() + STATE_WAIT_TIMEOUT_SEC
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/sessions/{session_id}/status").json()
        if snapshot["state"] == expected_state:
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"state never became {expected_state}")


def _decoded_session(make_client, **overrides):
    decoder = ControlledDecoder()
    decoder.release.set()
    client = make_client(load_decoder=lambda: decoder, **overrides)
    session_id = _upload(client).json()["session_id"]
    assert client.post(f"/api/sessions/{session_id}/decode").status_code == 202
    _wait_for_state(client, session_id, "finished")
    return client, session_id


def _session_dirs(settings) -> list[Path]:
    return list(settings.temp_root.iterdir()) if settings.temp_root.exists() else []


def test_health_reports_idle(make_client):
    response = make_client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "decoding": False}


def test_upload_rejects_non_video(make_client):
    response = _upload(make_client(), name="notes.txt", content=b"hello")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_upload_rejects_oversized_file(make_client, test_settings):
    client = make_client(settings=replace(test_settings, max_upload_bytes=1024))
    response = _upload(client)
    assert response.status_code == 413
    assert _session_dirs(test_settings) == []


def test_upload_stores_fixed_name_and_serves_range(make_client, test_settings):
    client = make_client()
    response = _upload(client, name="組員 的:影片?.MP4")
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "組員 的:影片?.MP4"
    assert body["size_bytes"] == len(FAKE_VIDEO_BYTES)
    assert body["video_url"] == f"/api/sessions/{body['session_id']}/video"
    [session_dir] = _session_dirs(test_settings)
    assert (session_dir / "input.mp4").is_file()

    ranged = client.get(body["video_url"], headers={"Range": "bytes=0-1023"})
    assert ranged.status_code == 206
    assert len(ranged.content) == 1024
    assert ranged.content == FAKE_VIDEO_BYTES[:1024]
    assert ranged.headers["content-type"] == "video/mp4"


def test_md5_is_computed_in_background(make_client):
    client = make_client()
    session_id = _upload(client).json()["session_id"]
    expected = hashlib.md5(FAKE_VIDEO_BYTES).hexdigest()
    deadline = time.monotonic() + STATE_WAIT_TIMEOUT_SEC
    while client.get(f"/api/sessions/{session_id}/status").json()["file_md5"] != expected:
        assert time.monotonic() < deadline
        time.sleep(0.02)


def test_busy_decoder_blocks_new_work(make_client):
    decoder = ControlledDecoder()
    client = make_client(load_decoder=lambda: decoder)
    session_id = _upload(client).json()["session_id"]
    assert client.post(f"/api/sessions/{session_id}/decode").json() == {"state": "decoding"}
    assert decoder.started.wait(STATE_WAIT_TIMEOUT_SEC)
    try:
        assert client.get("/api/health").json()["decoding"] is True
        assert client.post(f"/api/sessions/{session_id}/decode").status_code == 409
        assert _upload(client).status_code == 409
        assert client.delete(f"/api/sessions/{session_id}").status_code == 409
        assert client.get(f"/api/sessions/{session_id}/security").status_code == 409
    finally:
        decoder.release.set()
    _wait_for_state(client, session_id, "finished")
    assert client.post(f"/api/sessions/{session_id}/decode").status_code == 409


def test_tracks_served_with_audio_type_and_404_until_ready(make_client):
    decoder = ControlledDecoder()
    client = make_client(load_decoder=lambda: decoder)
    session_id = _upload(client).json()["session_id"]
    assert client.get(f"/api/sessions/{session_id}/tracks/en/chunk0").status_code == 404
    client.post(f"/api/sessions/{session_id}/decode")
    decoder.release.set()
    snapshot = _wait_for_state(client, session_id, "finished")
    for part_key, part in (("0", "chunk0"), ("full", "full")):
        url = snapshot["chunks"][part_key]["en"]
        assert url == f"/api/sessions/{session_id}/tracks/en/{part}"
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
    assert client.get(f"/api/sessions/{session_id}/tracks/en/chunk1").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/tracks/fr/full").status_code == 404


@pytest.mark.parametrize("path_template", [
    "/api/sessions/..%2F..%2F/video",
    "/api/sessions/{sid}/tracks/..%2F..%2Finput.mp4/full",
    "/api/sessions/{sid}/tracks/..%5C..%5Cinput.mp4/full",
    "/api/sessions/{sid}/tracks/en/..%2Fen.mp3",
    "/api/sessions/{sid}%2F..%2F{sid}/video",
    "/api/sessions/..%2F{sid}/status",
])
def test_path_traversal_is_404(make_client, path_template):
    client, session_id = _decoded_session(make_client)
    response = client.get(path_template.format(sid=session_id))
    assert response.status_code == 404
    assert b"ID3" not in response.content and FAKE_VIDEO_BYTES[:64] not in response.content


def test_delete_removes_directory_and_tracks(make_client, test_settings):
    client, session_id = _decoded_session(make_client)
    [session_dir] = _session_dirs(test_settings)
    assert client.delete(f"/api/sessions/{session_id}").json() == {"deleted": True}
    assert not session_dir.exists()
    assert client.get(f"/api/sessions/{session_id}/tracks/en/full").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/status").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}").status_code == 404


def test_new_upload_replaces_finished_session(make_client, test_settings):
    client, old_id = _decoded_session(make_client)
    [old_dir] = _session_dirs(test_settings)
    new_id = _upload(client).json()["session_id"]
    assert new_id != old_id
    assert not old_dir.exists()
    assert client.get(f"/api/sessions/{old_id}/status").status_code == 404


def test_locked_files_do_not_cause_500_and_are_cleared_at_shutdown(make_client, test_settings):
    is_locked = [True]

    def windows_like_remove(path):
        if is_locked[0]:
            raise PermissionError("[WinError 32] 檔案正由另一個程序使用")
        shutil.rmtree(path)

    remover = DirectoryRemover(remove_tree=windows_like_remove, sleep=lambda _s: None)
    client, session_id = _decoded_session(make_client, remover=remover)
    [session_dir] = _session_dirs(test_settings)
    assert client.delete(f"/api/sessions/{session_id}").status_code == 200
    assert session_dir.exists() and remover.pending_directories == [session_dir]
    assert client.get(f"/api/sessions/{session_id}/tracks/en/full").status_code == 404
    is_locked[0] = False
    client.__exit__(None, None, None)  # triggers lifespan shutdown
    assert not session_dir.exists()


def test_shutdown_removes_all_session_directories(make_client, test_settings):
    client = make_client()
    _upload(client)
    assert len(_session_dirs(test_settings)) == 1
    client.__exit__(None, None, None)
    assert _session_dirs(test_settings) == []


def test_security_requires_manifest(make_client):
    client = make_client()
    session_id = _upload(client).json()["session_id"]
    response = client.get(f"/api/sessions/{session_id}/security?ip_lock=true")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "manifest_not_ready"


def test_security_passes_manifest_and_accept_language(make_client):
    calls = []

    def fake_detect(available, system_languages, history, db_path, ip_lock_mode):
        calls.append((available, system_languages, history, db_path, ip_lock_mode))
        return FallbackDetection(track_key="en", source="P0 IP_LOCK_ENFORCED", metadata={"ip": "8.8.8.8", "country": "US"})

    client, session_id = _decoded_session(make_client, load_detector=lambda: fake_detect)
    response = client.get(
        f"/api/sessions/{session_id}/security?ip_lock=true",
        headers={"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ip_lock", "client_ip", "proxy", "country", "decision_source", "trust_level",
                         "recommended_track", "allowed_tracks", "file_md5"}
    assert body["allowed_tracks"] == ["en"]
    assert calls == [(["en"], ["zh-TW", "zh", "en"], None, None, True)]


def test_security_never_500_when_detector_crashes(make_client):
    def crashing_detect(*_args, **_kwargs):
        raise OSError("network unreachable")

    client, session_id = _decoded_session(make_client, load_detector=lambda: crashing_detect)
    response = client.get(f"/api/sessions/{session_id}/security?ip_lock=false")
    assert response.status_code == 200
    assert response.json()["decision_source"] == "THREAD_ERROR"
    assert response.json()["ip_lock"] is False


@pytest.mark.parametrize("origin, is_allowed", [
    ("http://localhost:5173", True),
    ("http://127.0.0.1:3000", True),
    ("http://localhost", True),
    ("http://evil.example.com", False),
    ("https://localhost:5173", False),
])
def test_cors_only_allows_local_origins(make_client, origin, is_allowed):
    response = make_client().options("/api/health", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET",
    })
    assert (response.headers.get("access-control-allow-origin") == origin) is is_allowed


def test_pack_router_reserved_without_endpoints(make_client):
    assert make_client().post("/api/pack").status_code == 404
