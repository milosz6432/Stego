"""GIF analysis: frame extraction, per-frame differences, palette/transparency.

Uses Pillow for robust frame decoding. Frames can be sent to the image LSB /
bitplane tools individually.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence


def analyse(path: str | Path) -> dict:
    img = Image.open(path)
    if img.format != "GIF":
        raise ValueError("Not a GIF file")

    frames = []
    prev = None
    n_frames = 0
    for i, frame in enumerate(ImageSequence.Iterator(img)):
        n_frames += 1
        rgba = frame.convert("RGBA")
        arr = np.array(rgba)
        changed = None
        if prev is not None and prev.shape == arr.shape:
            diff = np.abs(arr.astype(np.int16) - prev.astype(np.int16)).sum()
            changed = int(diff)
        frames.append({
            "index": i,
            "size": frame.size,
            "duration_ms": frame.info.get("duration", 0),
            "disposal": frame.info.get("disposal"),
            "diff_from_prev": changed,
        })
        prev = arr
        if i > 4096:
            break

    palette = None
    if img.getpalette():
        pal = img.getpalette()
        palette = {"entries": len(pal) // 3}
    return {
        "signature_ok": True,
        "frame_count": n_frames,
        "frames": frames,
        "loop": img.info.get("loop"),
        "transparency": img.info.get("transparency"),
        "palette": palette,
        "size": img.size,
    }


def extract_frame(path: str | Path, index: int) -> bytes:
    img = Image.open(path)
    for i, frame in enumerate(ImageSequence.Iterator(img)):
        if i == index:
            buf = io.BytesIO()
            frame.convert("RGBA").save(buf, format="PNG")
            return buf.getvalue()
    raise ValueError(f"Frame {index} not found")


def frame_count(path: str | Path) -> int:
    img = Image.open(path)
    return sum(1 for _ in ImageSequence.Iterator(img))
