"""Public URL builders, so the URL layout lives in exactly one place."""

API_PREFIX = "/api/sessions"


def build_video_url(session_id: str) -> str:
    return f"{API_PREFIX}/{session_id}/video"


def build_track_url(session_id: str, lang: str, part: str) -> str:
    return f"{API_PREFIX}/{session_id}/tracks/{lang}/{part}"
