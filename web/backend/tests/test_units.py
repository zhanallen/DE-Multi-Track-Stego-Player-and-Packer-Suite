"""Unit tests for pure logic (no HTTP, no real decoder)."""

import shutil
from pathlib import Path

import pytest

from web.backend.decode_worker import DecodeJob, ProgressReporter
from web.backend.errors import ApiError
from web.backend.file_cleanup import DirectoryRemover
from web.backend.lang_map import get_display_name
from web.backend.security_service import (
    FallbackDetection,
    build_security_report,
    detect_locale_safely,
    parse_accept_language,
)
from web.backend.session_store import Session, SessionState, TrackPart
from web.backend.upload_service import get_display_filename, get_video_suffix


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# ---- ProgressReporter -----------------------------------------------------
def test_progress_uses_bits_when_target_known():
    reporter = ProgressReporter(min_interval_sec=0.0, clock=FakeClock())
    payload = reporter.build_payload(current_frame=10, total_frames=100, bit_idx=8 * 1048576, target_bits=16 * 1048576)
    assert payload["percent"] == 50
    assert payload["payload_mb"] == 1.0
    assert payload["target_mb"] == 2.0


def test_progress_falls_back_to_frames_and_null_target_mb():
    reporter = ProgressReporter(min_interval_sec=0.0, clock=FakeClock())
    payload = reporter.build_payload(current_frame=25, total_frames=100, bit_idx=0, target_bits=0)
    assert payload["percent"] == 25
    assert payload["target_mb"] is None


@pytest.mark.parametrize("bit_idx, expected", [(0, 0), (1, 1), (99, 99), (100, 100), (150, 100)])
def test_progress_percent_boundaries(bit_idx, expected):
    reporter = ProgressReporter(min_interval_sec=0.0, clock=FakeClock())
    assert reporter.build_payload(1, 10, bit_idx, 100)["percent"] == expected


def test_progress_never_decreases():
    reporter = ProgressReporter(min_interval_sec=0.0, clock=FakeClock())
    first = reporter.build_payload(80, 100, 0, 0)["percent"]
    second = reporter.build_payload(90, 100, 10, 100)["percent"]
    assert first == 80 and second == 80


def test_progress_throttles_to_interval_and_computes_fps():
    clock = FakeClock()
    reporter = ProgressReporter(min_interval_sec=0.2, clock=clock)
    assert reporter.build_payload(10, 100, 0, 0) is not None
    clock.now = 0.1
    assert reporter.build_payload(20, 100, 0, 0) is None
    clock.now = 0.3
    payload = reporter.build_payload(30, 100, 0, 0)
    assert payload is not None
    assert payload["fps"] == pytest.approx(10 / 0.2)


# ---- helpers ----------------------------------------------------------------
@pytest.mark.parametrize("header, expected", [
    ("zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7", ["zh-TW", "zh", "en-US", "en"]),
    ("en;q=0.5, ja", ["ja", "en"]),
    ("*, fr;q=0", []),
    ("", []),
    (None, []),
    ("de;q=bad", []),
])
def test_parse_accept_language(header, expected):
    assert parse_accept_language(header) == expected


def test_display_name_lookup_and_fallback():
    assert "繁體中文" in get_display_name("zh-TW")
    assert get_display_name("xx") == "(xx) Track"


@pytest.mark.parametrize("raw, expected", [
    ("C:\\Users\\組員\\影片.MP4", "影片.MP4"),
    ("dir/sub/demo.mov", "demo.mov"),
    (None, ""),
])
def test_display_filename_strips_directories(raw, expected):
    assert get_display_filename(raw) == expected


@pytest.mark.parametrize("name", ["notes.txt", "video", "clip.mp4.exe"])
def test_video_suffix_rejects_non_video(name):
    with pytest.raises(ApiError) as caught:
        get_video_suffix(name)
    assert caught.value.status_code == 415


@pytest.mark.parametrize("name, suffix", [("a.mp4", ".mp4"), ("b.MOV", ".mov"), ("c.mkv", ".mkv")])
def test_video_suffix_accepts_allowed(name, suffix):
    assert get_video_suffix(name) == suffix


# ---- DirectoryRemover (Windows file-lock behaviour) ---------------------------
def test_remover_retries_then_defers_to_shutdown(tmp_path):
    locked_dir = tmp_path / "locked"
    locked_dir.mkdir()
    attempts, sleeps, is_locked = [], [], [True]

    def failing_remove(path: Path) -> None:
        attempts.append(path)
        if is_locked[0]:
            raise PermissionError("file in use")
        shutil.rmtree(path)

    remover = DirectoryRemover(retry_count=3, retry_delay_sec=0.5, remove_tree=failing_remove, sleep=sleeps.append)
    assert remover.remove(locked_dir) is False
    assert len(attempts) == 3
    assert sleeps == [0.5, 0.5]
    assert remover.pending_directories == [locked_dir]

    is_locked[0] = False  # e.g. the browser finally released the file
    remover.remove_pending()
    assert not locked_dir.exists()
    assert remover.pending_directories == []


def test_remover_treats_missing_directory_as_removed(tmp_path):
    assert DirectoryRemover().remove(tmp_path / "nope") is True


# ---- Session ------------------------------------------------------------------
def _make_session(tmp_path: Path) -> Session:
    session = Session("a" * 32, "demo.mp4", tmp_path, ".mp4")
    session.output_dir.mkdir()
    return session


def test_session_ignores_track_paths_outside_output_dir(tmp_path):
    session = _make_session(tmp_path)
    inside = session.output_dir / "en_chunk0.mp3"
    inside.write_bytes(b"x")
    session.record_chunk(0, False, {"en": str(inside), "evil": str(tmp_path.parent / "secret.mp3")})
    assert session.get_track_path("en", TrackPart.CHUNK0) == inside.resolve()
    assert session.get_track_path("evil", TrackPart.CHUNK0) is None


def test_session_rejects_second_decode(tmp_path):
    session = _make_session(tmp_path)
    session.begin_decoding()
    with pytest.raises(ApiError) as caught:
        session.begin_decoding()
    assert caught.value.status_code == 409


def test_log_history_is_capped(tmp_path):
    from web.backend.session_store import LogLevel
    session = _make_session(tmp_path)
    for index in range(250):
        session.append_log(LogLevel.INFO, f"line {index}")
    logs = session.build_snapshot()["logs"]
    assert len(logs) == 200
    assert logs[-1]["message"] == "line 249"


# ---- DecodeJob failure classification -----------------------------------------
def _raise_no_header(*_args, **_kwargs):
    raise ValueError("無效的檔案長度標頭")


def test_failure_before_manifest_is_no_payload(tmp_path):
    session = _make_session(tmp_path)
    session.begin_decoding()
    DecodeJob(session, _raise_no_header).run()
    assert session.state is SessionState.NO_PAYLOAD
    assert session.build_snapshot()["error"] is None


def test_failure_after_manifest_is_error(tmp_path):
    def decode_then_crash(*_args, on_manifest_ready, **_kwargs):
        on_manifest_ready({"initial_sec": 6.0, "tracks": [{"id": "en", "filename": "x_audio_en.mp3", "ext": ".mp3"}]})
        raise ValueError("zlib 解壓縮失敗")

    session = _make_session(tmp_path)
    session.begin_decoding()
    DecodeJob(session, decode_then_crash).run()
    snapshot = session.build_snapshot()
    assert session.state is SessionState.ERROR
    assert snapshot["error"] == "zlib 解壓縮失敗"
    assert snapshot["manifest"]["tracks"][0]["display_name"] == get_display_name("en")


def test_empty_result_without_manifest_is_no_payload(tmp_path):
    session = _make_session(tmp_path)
    session.begin_decoding()
    DecodeJob(session, lambda *_a, **_k: {}).run()
    assert session.state is SessionState.NO_PAYLOAD


def test_legacy_result_registers_full_tracks(tmp_path):
    session = _make_session(tmp_path)
    legacy_file = session.output_dir / "demo_audio_ja.mp3"
    legacy_file.write_bytes(b"x")
    session.begin_decoding()
    DecodeJob(session, lambda *_a, **_k: {"ja": str(legacy_file)}).run()
    assert session.state is SessionState.FINISHED
    assert session.get_track_path("ja", TrackPart.FULL) == legacy_file.resolve()
    assert session.get_available_langs() == ["ja"]


# ---- security report ----------------------------------------------------------
def test_detection_errors_become_thread_error():
    def broken_loader():
        raise ImportError("maxminddb missing")

    result = detect_locale_safely(broken_loader, ["zh-TW", "en"], [], None, True)
    report = build_security_report(result, True, None)
    assert report["decision_source"] == "THREAD_ERROR"
    assert report["recommended_track"] == "zh-TW"
    assert report["allowed_tracks"] == ["zh-TW"]
    assert report["trust_level"] == "❌ 執行緒異常"


def test_report_maps_metadata_fields():
    result = FallbackDetection(track_key="en", source="P0 IP_LOCK_ENFORCED", metadata={
        "ip": "1.2.3.4", "country": "US", "proxy_detected": True,
        "details": "HTTP proxy", "allowed_tracks": ["en", "en-US"],
    })
    report = build_security_report(result, True, "abc")
    assert report == {
        "ip_lock": True,
        "client_ip": "1.2.3.4",
        "proxy": {"enabled": True, "detail": "HTTP proxy"},
        "country": "US",
        "decision_source": "P0 IP_LOCK_ENFORCED",
        "trust_level": "🛡️ 頂級置信 (IP 區域強制鎖定)",
        "recommended_track": "en",
        "allowed_tracks": ["en", "en-US"],
        "file_md5": "abc",
    }
