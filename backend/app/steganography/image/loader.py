"""Image loading helpers shared by the image stego modules.

Loads via Pillow into a NumPy array, guards against decompression bombs, and
exposes channel metadata. The original file is never modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ...core import config

# Raise Pillow's bomb guard to our configured limit (still bounded).
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS


@dataclass
class LoadedImage:
    array: np.ndarray        # H x W x C, uint8 (or uint16 for 16-bit)
    mode: str                # Pillow mode of the working array: L, RGB, RGBA, ...
    width: int
    height: int
    channels: list[str]      # e.g. ["R","G","B"]
    original_mode: str

    @property
    def nchannels(self) -> int:
        return len(self.channels)


_MODE_CHANNELS = {
    "L": ["L"],
    "LA": ["L", "A"],
    "P": ["P"],
    "RGB": ["R", "G", "B"],
    "RGBA": ["R", "G", "B", "A"],
    "CMYK": ["C", "M", "Y", "K"],
    "I": ["I"],
    "I;16": ["I"],
    "F": ["F"],
}


def load_image(path: str | Path, *, keep_palette: bool = False) -> LoadedImage:
    img = Image.open(path)
    original_mode = img.mode

    if img.width * img.height > config.MAX_IMAGE_PIXELS:
        raise ValueError(
            f"Image too large ({img.width}x{img.height}); limit is {config.MAX_IMAGE_PIXELS} pixels"
        )

    # Palette images: keep indices if asked (for palette-LSB), else expand.
    if img.mode == "P" and not keep_palette:
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")

    arr = np.array(img)
    if arr.ndim == 2:
        arr = arr[:, :, np.newaxis]

    channels = _MODE_CHANNELS.get(img.mode)
    if channels is None:
        channels = [f"C{i}" for i in range(arr.shape[2])]

    return LoadedImage(
        array=arr,
        mode=img.mode,
        width=img.width,
        height=img.height,
        channels=channels,
        original_mode=original_mode,
    )


def channel_index(loaded: LoadedImage, name: str) -> int:
    name = name.upper()
    for i, c in enumerate(loaded.channels):
        if c.upper() == name:
            return i
    raise ValueError(f"Channel {name!r} not present (have {loaded.channels})")
