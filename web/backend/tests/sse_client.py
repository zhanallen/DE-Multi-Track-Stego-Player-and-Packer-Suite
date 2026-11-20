"""Minimal threaded SSE reader for tests (EventSource stand-in)."""

import json
import queue
import threading

import httpx


class SseReader:
    def __init__(self, url: str):
        self._url = url
        self._events: queue.Queue = queue.Queue()
        self._is_closing = threading.Event()
        self._connected = threading.Event()
        self._client = httpx.Client(timeout=httpx.Timeout(10.0, read=None))
        self._response: httpx.Response | None = None
        self._thread = threading.Thread(target=self._read_loop, daemon=True)

    def __enter__(self) -> "SseReader":
        self._thread.start()
        self._connected.wait(timeout=10)
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        """Simulates the browser tab going away (drops the TCP connection)."""
        self._is_closing.set()
        if self._response is not None:
            self._response.close()
        self._client.close()
        self._thread.join(timeout=10)

    def next_event(self, timeout_sec: float = 60.0) -> tuple[str, dict]:
        return self._events.get(timeout=timeout_sec)

    def collect_until(self, terminal_names: set[str], timeout_sec: float = 300.0) -> list[tuple[str, dict]]:
        collected = []
        while True:
            name, data = self.next_event(timeout_sec)
            collected.append((name, data))
            if name in terminal_names:
                return collected

    def _read_loop(self) -> None:
        try:
            with self._client.stream("GET", self._url) as response:
                self._response = response
                self._connected.set()
                response.raise_for_status()
                self._parse_lines(response.iter_lines())
        except Exception:
            # Closing the response from another thread surfaces as different
            # errors per OS (e.g. WinError 10053 on Windows); only real failures matter.
            if not self._is_closing.is_set():
                raise
        finally:
            self._connected.set()

    def _parse_lines(self, lines) -> None:
        name, data_lines = None, []
        for line in lines:
            if line.startswith("event:"):
                name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
            elif line == "" and name is not None:
                self._events.put((name, json.loads("\n".join(data_lines))))
                name, data_lines = None, []
