"""Background MD5 of the uploaded video (Zero-Trust panel, same as Qt player)."""

import hashlib
import logging
import threading
from pathlib import Path

from .session_store import Session

logger = logging.getLogger(__name__)

READ_BLOCK_BYTES = 81920


def compute_file_md5(path: Path) -> str:
    md5_hash = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(READ_BLOCK_BYTES), b""):
            md5_hash.update(block)
    return md5_hash.hexdigest()


def start_md5_computation(session: Session) -> threading.Thread:
    def compute() -> None:
        try:
            session.set_file_md5(compute_file_md5(session.video_path))
        except OSError as error:
            # The session may have been replaced and its directory removed meanwhile.
            logger.warning("MD5 計算失敗：%s", error)

    thread = threading.Thread(target=compute, name="md5", daemon=True)
    thread.start()
    return thread
