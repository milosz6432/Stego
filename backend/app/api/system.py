"""System / capability endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..core import tools

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/tools")
def tool_registry():
    """Which optional external tools are installed."""
    return {"tools": tools.registry()}
