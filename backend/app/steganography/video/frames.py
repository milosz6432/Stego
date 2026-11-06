"""Frame extraction and contact sheets via ffmpeg.

Frames are decoded to PNG on demand into a per-file cache directory. We never
load the whole video into memory — ffmpeg streams to disk. Extracted frames
can be sent to the image module for LSB/bitplane analysis.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from ...core import config, tools
from ...core.job_manager import ProgressHandle
from ...core.tools import ToolNotAvailable, run_tool
from . import info as vinfo


def _ensure_ffmpeg() -> None:
    if not tools.available("ffmpeg"):
        raise ToolNotAvailable("ffmpeg")


def extract_frame_at(path: str | Path, timestamp: float, out_dir: str | Path) -> Path:
    """Extract a single frame at *timestamp* seconds as PNG."""
    _ensure_ffmpeg()
    out = Path(out_dir) / f"frame_t{timestamp:.3f}.png"
    args = ["-v", "error", "-ss", str(timestamp), "-i", str(path),
            "-frames:v", "1", "-y", str(out)]
    res = run_tool("ffmpeg", args, timeout=120)
    if not res.ok or not out.exists():
        raise ValueError(f"ffmpeg failed to extract frame: {res.stderr[:300]}")
    return out


def extract_every_n(path: str | Path, out_dir: str | Path, *, n: int = 30,
                    max_frames: Optional[int] = None,
                    progress: Optional[ProgressHandle] = None) -> list[dict]:
    """Extract every n-th frame using a select filter."""
    _ensure_ffmpeg()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    limit = min(max_frames or config.MAX_FRAMES_EXTRACT, config.MAX_FRAMES_EXTRACT)
    pattern = str(out_dir / "frame_%06d.png")
    vf = f"select=not(mod(n\\,{max(1, n)}))"
    args = ["-v", "error", "-i", str(path), "-vf", vf, "-vsync", "vfr",
            "-frames:v", str(limit), "-y", pattern]
    res = run_tool("ffmpeg", args, timeout=600)
    if not res.ok:
        raise ValueError(f"ffmpeg frame extraction failed: {res.stderr[:300]}")
    return _list_frames(out_dir)


def extract_interval(path: str | Path, out_dir: str | Path, *, interval: float = 1.0,
                     max_frames: Optional[int] = None) -> list[dict]:
    """Extract one frame every *interval* seconds."""
    _ensure_ffmpeg()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    limit = min(max_frames or config.MAX_FRAMES_EXTRACT, config.MAX_FRAMES_EXTRACT)
    fps = 1.0 / max(interval, 0.001)
    pattern = str(out_dir / "frame_%06d.png")
    args = ["-v", "error", "-i", str(path), "-vf", f"fps={fps}",
            "-frames:v", str(limit), "-y", pattern]
    res = run_tool("ffmpeg", args, timeout=600)
    if not res.ok:
        raise ValueError(f"ffmpeg interval extraction failed: {res.stderr[:300]}")
    return _list_frames(out_dir)


def scene_detect(path: str | Path, out_dir: str | Path, *, threshold: float = 0.3,
                 max_frames: Optional[int] = None) -> list[dict]:
    """Extract frames at scene changes (ffmpeg select='gt(scene,threshold)')."""
    _ensure_ffmpeg()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    limit = min(max_frames or 500, config.MAX_FRAMES_EXTRACT)
    pattern = str(out_dir / "scene_%06d.png")
    vf = f"select=gt(scene\\,{threshold})"
    args = ["-v", "error", "-i", str(path), "-vf", vf, "-vsync", "vfr",
            "-frames:v", str(limit), "-y", pattern]
    res = run_tool("ffmpeg", args, timeout=600)
    if not res.ok:
        raise ValueError(f"ffmpeg scene detection failed: {res.stderr[:300]}")
    return _list_frames(out_dir, prefix="scene_")


def contact_sheet(path: str | Path, out_dir: str | Path, *, cols: int = 5, rows: int = 5,
                  width: int = 1200) -> bytes:
    """Build a tiled montage of evenly-spaced frames."""
    _ensure_ffmpeg()
    duration = float(vinfo.probe(path).get("format", {}).get("duration") or 0) or 0
    n = cols * rows
    tmp = Path(out_dir) / "_sheet_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    frames = []
    if duration > 0:
        for i in range(n):
            ts = duration * (i + 0.5) / n
            try:
                frames.append(extract_frame_at(path, ts, tmp))
            except ValueError:
                pass
    else:  # fall back to first N frames
        frames = [Path(f["path"]) for f in extract_every_n(path, tmp, n=1, max_frames=n)]

    if not frames:
        raise ValueError("Could not extract frames for contact sheet")
    thumbs = [Image.open(f).convert("RGB") for f in frames]
    tw = width // cols
    th = int(tw * thumbs[0].height / thumbs[0].width)
    sheet = Image.new("RGB", (tw * cols, th * rows), (17, 17, 20))
    for idx, thumb in enumerate(thumbs):
        thumb = thumb.resize((tw, th), Image.BILINEAR)
        r, c = divmod(idx, cols)
        sheet.paste(thumb, (c * tw, r * th))
    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()


def _list_frames(out_dir: Path, prefix: str = "frame_") -> list[dict]:
    frames = sorted(out_dir.glob(f"{prefix}*.png"))
    return [{"index": i, "path": str(p), "name": p.name} for i, p in enumerate(frames)]


def frame_png(path: Path) -> bytes:
    return Path(path).read_bytes()
