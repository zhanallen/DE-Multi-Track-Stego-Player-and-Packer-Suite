"""FastAPI entry point.

Start from the repository root:
    uvicorn web.backend.main:app --host 127.0.0.1 --port 8765
"""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .errors import register_error_handlers
from .routers import pack

LOCAL_ORIGIN_PATTERN = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"


def _make_console_output_safe() -> None:
    # pee_stego prints emoji; a cp950 Windows console would raise UnicodeEncodeError
    # inside the decode thread. Replacing unencodable characters keeps decoding alive.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = FastAPI(title="StegoPlayer Web API", lifespan=lifespan)
    app.state.settings = active_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN_PATTERN,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(pack.router)

    @app.get("/api/health")
    def get_health() -> dict:
        return {"status": "ok", "decoding": False}

    return app


_make_console_output_safe()
app = create_app()
