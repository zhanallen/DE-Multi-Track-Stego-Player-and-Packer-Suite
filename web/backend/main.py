"""FastAPI entry point.

Start from the repository root:
    uvicorn web.backend.main:app --host 127.0.0.1 --port 8765
"""

import sys
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .decode_worker import DecodeFunction, load_default_decoder
from .dependencies import get_store
from .errors import register_error_handlers
from .file_cleanup import DirectoryRemover
from .routers import pack, security, sessions
from .security_service import DetectFunction, load_default_detector
from .session_store import SessionStore

LOCAL_ORIGIN_PATTERN = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"


def _make_console_output_safe() -> None:
    # pee_stego prints emoji; a cp950 Windows console would raise UnicodeEncodeError
    # inside the decode thread. Replacing unencodable characters keeps decoding alive.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


def create_app(
    settings: Settings | None = None,
    load_decoder: Callable[[], DecodeFunction] = load_default_decoder,
    load_detector: Callable[[], DetectFunction] = load_default_detector,
) -> FastAPI:
    active_settings = settings or Settings.from_environment()
    store = SessionStore(active_settings.temp_root, DirectoryRemover())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.remove_all()

    app = FastAPI(title="StegoPlayer Web API", lifespan=lifespan)
    app.state.settings = active_settings
    app.state.store = store
    app.state.load_decoder = load_decoder
    app.state.load_detector = load_detector
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN_PATTERN,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(sessions.router)
    app.include_router(security.router)
    app.include_router(pack.router)

    @app.get("/api/health")
    def get_health(session_store: SessionStore = Depends(get_store)) -> dict:
        return {"status": "ok", "decoding": session_store.is_decoding()}

    return app


_make_console_output_safe()
app = create_app()
