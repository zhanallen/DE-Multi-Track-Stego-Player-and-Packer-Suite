"""Accessors for objects that ``create_app`` stores on ``app.state``."""

from fastapi import Request

from .config import Settings
from .session_store import SessionStore


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_decoder_loader(request: Request):
    """Callable returning the decode function (lazy so Numba loads on first use)."""
    return request.app.state.load_decoder


def get_detector_loader(request: Request):
    """Callable returning ``detect_best_locale`` (or a test double)."""
    return request.app.state.load_detector
