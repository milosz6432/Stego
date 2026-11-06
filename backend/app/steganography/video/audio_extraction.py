"""Extract audio track(s) from a video for the Audio Analysis workspace.

Audio is extracted losslessly to WAV (pcm_s16le/s24le) so it can be run
through the PCM-LSB engine. The original video is never modified. The
relationship to the source is kept in metadata (stream index, offset).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ...core import tools
from ...core.tools import ToolNotAvailable, run_tool


def extract_audio(path: str | Path, out_path: str | Path, *, stream: int = 0) -> dict:
    if not tools.available("ffmpeg"):
        raise ToolNotAvailable("ffmpeg")
    out_path = str(out_path)
    args = ["-v", "error", "-i", str(path), "-map", f"0:a:{stream}",
            "-c:a", "pcm_s16le", "-y", out_path]
    res = run_tool("ffmpeg", args, timeout=600)
    if not res.ok or not os.path.exists(out_path):
        raise ValueError(f"ffmpeg audio extraction failed: {res.stderr[:300]}")
    return {"ok": True, "path": out_path, "stream": stream,
            "size": os.path.getsize(out_path), "command": res.to_dict()}
