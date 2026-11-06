"""Application configuration.

All runtime paths and limits live here. Values can be overridden with
environment variables (prefix ``STEGO_``) so the app is usable without
editing source.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_path(name: str, default: Path) -> Path:
    val = os.environ.get(name)
    return Path(val).expanduser().resolve() if val else default


# Root of the backend package (…/backend)
BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Where uploads, working copies and extracted payloads live. This whole tree
# is disposable and git-ignored.
DATA_DIR = _env_path("STEGO_DATA_DIR", BACKEND_ROOT / "data")
UPLOAD_DIR = DATA_DIR / "uploads"          # immutable originals (one dir per file)
WORK_DIR = DATA_DIR / "work"               # scratch working copies
EXTRACT_DIR = DATA_DIR / "extracted"       # recovered payloads
CACHE_DIR = DATA_DIR / "cache"             # rendered previews (bitplanes, spectrograms)

# Upload limits
MAX_UPLOAD_BYTES = _env_int("STEGO_MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024)  # 2 GiB

# Subprocess execution limits for external tools
TOOL_TIMEOUT_SECONDS = _env_int("STEGO_TOOL_TIMEOUT", 120)
TOOL_MAX_OUTPUT_BYTES = _env_int("STEGO_TOOL_MAX_OUTPUT", 8 * 1024 * 1024)

# Analysis safety limits
MAX_IMAGE_PIXELS = _env_int("STEGO_MAX_IMAGE_PIXELS", 80_000_000)  # 80 MP
MAX_LSB_OUTPUT_BYTES = _env_int("STEGO_MAX_LSB_OUTPUT", 64 * 1024 * 1024)
MAX_AUDIO_SECONDS = _env_int("STEGO_MAX_AUDIO_SECONDS", 3600)
MAX_FRAMES_EXTRACT = _env_int("STEGO_MAX_FRAMES", 2000)

# CORS origins for the dev frontend
CORS_ORIGINS = os.environ.get(
    "STEGO_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")


def ensure_dirs() -> None:
    for d in (DATA_DIR, UPLOAD_DIR, WORK_DIR, EXTRACT_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
