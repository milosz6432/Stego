"""Bit-plane visualisation.

For each channel and bit position (0=LSB … 7=MSB) we render a 1-bit image
where set bits are white. Noise-looking planes are "normal"; structured
content in a low plane is a strong steganography indicator, so we also compute
a quick structure score per plane.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from .loader import LoadedImage, load_image, channel_index


def _plane_bits(samples: np.ndarray, bit: int) -> np.ndarray:
    return ((samples >> bit) & 1).astype(np.uint8)


def _structure_score(plane: np.ndarray) -> float:
    """Heuristic 0..1: how non-random a bit plane looks.

    A uniformly random LSB plane has ~0.5 set-fraction and high local
    disagreement between neighbours. Structured/hidden content lowers the
    neighbour-disagreement rate. We combine horizontal+vertical transition
    rates; lower transitions => higher score.
    """
    if plane.size < 16:
        return 0.0
    h_trans = np.mean(plane[:, 1:] != plane[:, :-1])
    v_trans = np.mean(plane[1:, :] != plane[:-1, :])
    trans = (h_trans + v_trans) / 2.0
    # random ~0.5 transitions -> score 0; fully flat -> score 1
    return float(max(0.0, 1.0 - 2.0 * trans))


def _render_png(plane: np.ndarray, *, contrast: bool, invert: bool, scale: float = 1.0) -> bytes:
    img8 = (plane * 255).astype(np.uint8)
    if invert:
        img8 = 255 - img8
    im = Image.fromarray(img8, mode="L")
    if scale != 1.0 and scale > 0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                       Image.NEAREST)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def available_planes(loaded: LoadedImage) -> list[str]:
    return [c for c in loaded.channels if c in ("R", "G", "B", "A", "L")]


def render_plane(
    path: str | Path,
    channel: str,
    bit: int,
    *,
    invert: bool = False,
    contrast: bool = True,
    max_dim: int = 1600,
) -> tuple[bytes, dict]:
    loaded = load_image(path)
    ci = channel_index(loaded, channel)
    samples = loaded.array[:, :, ci].astype(np.uint8)
    plane = _plane_bits(samples, bit)
    score = _structure_score(plane)
    scale = 1.0
    if max(loaded.width, loaded.height) > max_dim:
        scale = max_dim / max(loaded.width, loaded.height)
    png = _render_png(plane, contrast=contrast, invert=invert, scale=scale)
    meta = {
        "channel": channel,
        "bit": bit,
        "set_fraction": float(plane.mean()),
        "structure_score": round(score, 4),
        "width": loaded.width,
        "height": loaded.height,
        "scaled": scale != 1.0,
    }
    return png, meta


def overview(path: str | Path) -> dict:
    """Score every channel/bit plane so the UI can flag suspicious ones."""
    loaded = load_image(path)
    results = []
    for ch in available_planes(loaded):
        ci = channel_index(loaded, ch)
        samples = loaded.array[:, :, ci].astype(np.uint8)
        for bit in range(8):
            plane = _plane_bits(samples, bit)
            results.append({
                "channel": ch,
                "bit": bit,
                "set_fraction": round(float(plane.mean()), 4),
                "structure_score": round(_structure_score(plane), 4),
            })
    results.sort(key=lambda r: r["structure_score"], reverse=True)
    return {
        "width": loaded.width,
        "height": loaded.height,
        "channels": loaded.channels,
        "planes": results,
        "suspicious": [r for r in results if r["bit"] <= 2 and r["structure_score"] > 0.15],
    }
