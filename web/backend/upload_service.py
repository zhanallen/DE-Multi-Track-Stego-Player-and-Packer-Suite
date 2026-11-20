"""Upload validation and size-limited copy to the session directory."""

from pathlib import Path, PureWindowsPath
from typing import BinaryIO

from .config import ALLOWED_VIDEO_SUFFIXES, UPLOAD_COPY_BUFFER_BYTES
from .errors import ApiError


class UploadTooLargeError(ApiError):
    def __init__(self, max_bytes: int):
        super().__init__(413, "file_too_large", f"檔案超過上限 {max_bytes // (1024 * 1024)} MB")


def get_display_filename(raw_filename: str | None) -> str:
    # PureWindowsPath strips both "\" and "/" directory parts some clients send.
    return PureWindowsPath(raw_filename or "").name


def get_video_suffix(display_filename: str) -> str:
    suffix = PureWindowsPath(display_filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        allowed = "、".join(ALLOWED_VIDEO_SUFFIXES)
        raise ApiError(415, "unsupported_media_type", f"僅支援 {allowed} 影片")
    return suffix


def copy_upload(source: BinaryIO, destination: Path, max_bytes: int) -> int:
    """Copy the uploaded stream; raises UploadTooLargeError past ``max_bytes``."""
    written = 0
    with destination.open("wb") as target:
        while block := source.read(UPLOAD_COPY_BUFFER_BYTES):
            written += len(block)
            if written > max_bytes:
                raise UploadTooLargeError(max_bytes)
            target.write(block)
    return written
