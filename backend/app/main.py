"""STEGO LAB FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000  (from the backend dir)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .core import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("stego")

config.ensure_dirs()

app = FastAPI(
    title="STEGO LAB",
    description="Advanced CTF steganography analysis workbench",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# Routers ---------------------------------------------------------------------
from .api import files, jobs, system  # noqa: E402
from .api import image as image_api  # noqa: E402
from .api import audio as audio_api  # noqa: E402
from .api import video as video_api  # noqa: E402
from .api import extraction as extraction_api  # noqa: E402
from .api import smart_scan as smart_scan_api  # noqa: E402

for r in (
    system.router,
    files.router,
    jobs.router,
    image_api.router,
    audio_api.router,
    video_api.router,
    extraction_api.router,
    smart_scan_api.router,
):
    app.include_router(r)


@app.get("/")
def root():
    return {"name": "STEGO LAB", "version": __version__, "docs": "/docs"}
