"""Reserved for the future StegoPacker web version (POST /api/pack ...).

Intentionally registers no endpoints yet; main.py already mounts this router
under ``/api/pack`` so adding the packer later will not touch other modules.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/pack", tags=["pack"])
