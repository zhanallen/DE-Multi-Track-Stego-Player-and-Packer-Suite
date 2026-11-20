"""Directory removal that tolerates Windows file locks.

On Windows a file being streamed to the browser cannot be deleted. Instead of
failing the request we retry a few times, then remember the directory and try
again when the server shuts down.
"""

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .config import DELETE_RETRY_COUNT, DELETE_RETRY_DELAY_SEC

logger = logging.getLogger(__name__)


class DirectoryRemover:
    def __init__(
        self,
        retry_count: int = DELETE_RETRY_COUNT,
        retry_delay_sec: float = DELETE_RETRY_DELAY_SEC,
        remove_tree: Callable[[Path], None] = shutil.rmtree,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._retry_count = retry_count
        self._retry_delay_sec = retry_delay_sec
        self._remove_tree = remove_tree
        self._sleep = sleep
        self._lock = threading.Lock()
        self._pending: set[Path] = set()

    def remove(self, directory: Path) -> bool:
        """Return True when the directory is gone; never raises."""
        for attempt in range(1, self._retry_count + 1):
            if self._try_remove(directory):
                return True
            if attempt < self._retry_count:
                self._sleep(self._retry_delay_sec)
        logger.warning("無法刪除暫存目錄 %s（檔案可能仍被開啟），將於伺服器關閉時再清一次", directory)
        with self._lock:
            self._pending.add(directory)
        return False

    def remove_pending(self) -> None:
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
        for directory in pending:
            if not self._try_remove(directory):
                logger.warning("關閉時仍無法刪除暫存目錄 %s", directory)

    @property
    def pending_directories(self) -> list[Path]:
        with self._lock:
            return sorted(self._pending)

    def _try_remove(self, directory: Path) -> bool:
        if not directory.exists():
            return True
        try:
            self._remove_tree(directory)
        except OSError as error:
            logger.info("刪除 %s 失敗：%s", directory, error)
        return not directory.exists()
