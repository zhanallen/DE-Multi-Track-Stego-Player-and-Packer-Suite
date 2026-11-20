import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from web.backend.config import Settings
from web.backend.decode_worker import load_default_decoder
from web.backend.main import create_app
from web.backend.tests import fixtures

SERVER_START_TIMEOUT_SEC = 15


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def stego_video(media_dir) -> Path:
    return fixtures.resolve_stego_sample(media_dir / "stego")


@pytest.fixture(scope="session")
def plain_video(media_dir) -> Path:
    return fixtures.build_plain_video(media_dir / "plain")


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=0,
        temp_root=tmp_path / "sessions",
        max_upload_bytes=50 * 1024 * 1024,
        geoip_db_path=tmp_path / "missing.mmdb",
        sse_heartbeat_sec=1.0,
    )


@pytest.fixture
def make_client(test_settings) -> Iterator[Callable[..., TestClient]]:
    """Build an in-process TestClient around create_app with injected doubles."""
    clients: list[TestClient] = []

    def build(**overrides) -> TestClient:
        settings = overrides.pop("settings", test_settings)
        client = TestClient(create_app(settings=settings, **overrides))
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@dataclass
class LiveServer:
    base_url: str
    settings: Settings

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def start_live_server(test_settings) -> Iterator[Callable[..., LiveServer]]:
    """Run the real app on a real socket (SSE needs true streaming)."""
    servers: list[tuple[uvicorn.Server, threading.Thread]] = []

    def start(load_decoder=load_default_decoder, **overrides) -> LiveServer:
        port = _find_free_port()
        settings = replace(test_settings, port=port)
        app = create_app(settings=settings, load_decoder=load_decoder, **overrides)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + SERVER_START_TIMEOUT_SEC
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.05)
        servers.append((server, thread))
        return LiveServer(base_url=f"http://127.0.0.1:{port}", settings=settings)

    yield start
    for server, thread in servers:
        server.should_exit = True
        thread.join(timeout=10)
