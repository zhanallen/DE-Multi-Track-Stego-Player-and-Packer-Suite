"""Synthetic media for tests.

When ``STEGO_SAMPLE`` is unset we build a ~3 s cover video plus two sine-wave
tracks named ``*_audio_<lang>.mp3`` and pack them with the real
``stego_facade.encode_video_multi``, so integration tests never need to skip.
"""

import os
import subprocess
from pathlib import Path

import imageio_ffmpeg

from web.backend.config import ensure_src_on_path

STEGO_SAMPLE_ENV = "STEGO_SAMPLE"
COVER_DURATION_SEC = 3
COVER_SIZE = "640x360"
COVER_FPS = 30
# Audio longer than the video payload window so decoding spans >10 frames and
# the engine fires at least one progress callback (it reports every 10 frames).
TRACK_DURATION_SEC = 6
INITIAL_CHUNK_SEC = 2.0
TRACK_FREQUENCIES = {"zh-TW": 440, "en": 880}


def _run_ffmpeg(arguments: list[str]) -> None:
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", *arguments]
    subprocess.run(command, check=True, capture_output=True)


def generate_cover_video(destination: Path) -> Path:
    source = f"testsrc2=size={COVER_SIZE}:rate={COVER_FPS}:duration={COVER_DURATION_SEC}"
    _run_ffmpeg(["-f", "lavfi", "-i", source, "-pix_fmt", "yuv420p", "-c:v", "libx264", str(destination)])
    return destination


def generate_sine_track(destination: Path, frequency: int) -> Path:
    source = f"sine=frequency={frequency}:duration={TRACK_DURATION_SEC}"
    _run_ffmpeg(["-f", "lavfi", "-i", source, "-c:a", "libmp3lame", "-b:a", "64k", str(destination)])
    return destination


def build_stego_video(work_dir: Path) -> Path:
    ensure_src_on_path()
    import stego_facade

    work_dir.mkdir(parents=True, exist_ok=True)
    cover = generate_cover_video(work_dir / "cover.mp4")
    tracks = [
        generate_sine_track(work_dir / f"demo_audio_{lang}.mp3", frequency)
        for lang, frequency in TRACK_FREQUENCIES.items()
    ]
    output = work_dir / "stego.mp4"
    stego_facade.encode_video_multi(
        str(cover), [str(track) for track in tracks], str(output), initial_sec=INITIAL_CHUNK_SEC
    )
    return output


def build_plain_video(work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    return generate_cover_video(work_dir / "plain.mp4")


def resolve_stego_sample(work_dir: Path) -> Path:
    sample = os.environ.get(STEGO_SAMPLE_ENV)
    if sample:
        return Path(sample)
    return build_stego_video(work_dir)
