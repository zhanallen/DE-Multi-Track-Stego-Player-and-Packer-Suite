"""Content-Type lookup for the files we stream back."""

from pathlib import Path

AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/mp4",
    ".webm": "audio/webm",
    ".wav": "audio/wav",
}
VIDEO_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}
FALLBACK_MEDIA_TYPE = "application/octet-stream"


def get_audio_media_type(path: Path) -> str:
    return AUDIO_MEDIA_TYPES.get(path.suffix.lower(), FALLBACK_MEDIA_TYPE)


def get_video_media_type(path: Path) -> str:
    return VIDEO_MEDIA_TYPES.get(path.suffix.lower(), FALLBACK_MEDIA_TYPE)
