"""Image channel analysis and reversible transforms.

All operations read the immutable original and produce new rendered images;
the source file is never changed. Outputs are returned as PNG bytes plus
numeric summaries (histograms) for Plotly.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from .loader import LoadedImage, load_image, channel_index


def _to_png(arr: np.ndarray, mode: Optional[str] = None) -> bytes:
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    im = Image.fromarray(arr, mode=mode)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def histograms(path: str | Path) -> dict:
    loaded = load_image(path)
    out = {}
    for i, ch in enumerate(loaded.channels):
        samples = loaded.array[:, :, i].astype(np.uint8).ravel()
        hist = np.bincount(samples, minlength=256).tolist()
        out[ch] = hist
    return {"channels": loaded.channels, "histograms": out,
            "width": loaded.width, "height": loaded.height}


def isolate_channel(path: str | Path, channel: str, *, grayscale: bool = True) -> bytes:
    loaded = load_image(path)
    ci = channel_index(loaded, channel)
    plane = loaded.array[:, :, ci].astype(np.uint8)
    if grayscale:
        return _to_png(plane, mode="L")
    # colourised: place the channel in its own colour slot
    rgb = np.zeros((loaded.height, loaded.width, 3), dtype=np.uint8)
    slot = {"R": 0, "G": 1, "B": 2}.get(channel.upper())
    if slot is not None:
        rgb[:, :, slot] = plane
    else:
        rgb[:] = plane[:, :, None]
    return _to_png(rgb, mode="RGB")


def transform(
    path: str | Path,
    *,
    invert: bool = False,
    grayscale: bool = False,
    brightness: float = 0.0,     # -255..255 additive
    contrast: float = 1.0,       # multiplicative around 128
    gamma: float = 1.0,
    bit_mask: Optional[int] = None,  # AND each sample with this (e.g. 0x0F)
) -> bytes:
    loaded = load_image(path)
    arr = loaded.array.astype(np.float64)
    rgb = arr[:, :, :3] if arr.shape[2] >= 3 else arr

    if bit_mask is not None:
        rgb = np.bitwise_and(rgb.astype(np.int32), int(bit_mask)).astype(np.float64)
    if contrast != 1.0:
        rgb = (rgb - 128.0) * contrast + 128.0
    if brightness:
        rgb = rgb + brightness
    if gamma and gamma != 1.0:
        rgb = 255.0 * np.power(np.clip(rgb, 0, 255) / 255.0, 1.0 / gamma)
    if invert:
        rgb = 255.0 - rgb
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    if grayscale:
        if rgb.shape[2] >= 3:
            gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
            return _to_png(gray.astype(np.uint8), mode="L")
        return _to_png(rgb[:, :, 0], mode="L")
    if rgb.shape[2] == 1:
        return _to_png(rgb[:, :, 0], mode="L")
    return _to_png(rgb[:, :, :3], mode="RGB")


def channel_difference(path: str | Path, ch_a: str, ch_b: str, *, amplify: int = 1) -> bytes:
    loaded = load_image(path)
    a = loaded.array[:, :, channel_index(loaded, ch_a)].astype(np.int16)
    b = loaded.array[:, :, channel_index(loaded, ch_b)].astype(np.int16)
    diff = np.abs(a - b) * max(1, amplify)
    return _to_png(np.clip(diff, 0, 255).astype(np.uint8), mode="L")


def image_difference(path_a: str | Path, path_b: str | Path, *, amplify: int = 1) -> bytes:
    a = load_image(path_a).array[:, :, :3].astype(np.int16)
    b = load_image(path_b).array[:, :, :3].astype(np.int16)
    if a.shape != b.shape:
        raise ValueError(f"Image shapes differ: {a.shape} vs {b.shape}")
    diff = np.abs(a - b) * max(1, amplify)
    return _to_png(np.clip(diff, 0, 255).astype(np.uint8), mode="RGB")


def statistics(path: str | Path) -> dict:
    """Per-channel stats + chi-square LSB test (a classic steganalysis cue)."""
    loaded = load_image(path)
    out = {}
    for i, ch in enumerate(loaded.channels):
        samples = loaded.array[:, :, i].astype(np.uint8).ravel()
        hist = np.bincount(samples, minlength=256).astype(np.float64)
        # Chi-square on pairs (2k, 2k+1): under LSB stego their counts equalise.
        even = hist[0::2]
        odd = hist[1::2]
        expected = (even + odd) / 2.0
        mask = expected > 0
        chi = float(np.sum((even[mask] - expected[mask]) ** 2 / expected[mask]))
        out[ch] = {
            "mean": round(float(samples.mean()), 3),
            "std": round(float(samples.std()), 3),
            "min": int(samples.min()),
            "max": int(samples.max()),
            "lsb_chi_square": round(chi, 2),
            "lsb_set_fraction": round(float((samples & 1).mean()), 4),
        }
    return {"channels": loaded.channels, "stats": out}
