"""Configurable LSB / bit-plane extraction engine for images.

This is intentionally general rather than one hardcoded "LSB" method. A CTF
payload can be hidden with any combination of:

  * which bit position(s) per pixel sample (plane 0 = LSB … 7 = MSB),
  * which channels and in what order,
  * pixel traversal order (row-major vs column-major),
  * bit output order within a byte (MSB-first vs LSB-first),
  * how channels interleave (per-pixel across channels, or channel-by-channel).

The engine turns the selected bits into a byte stream and offers several text
decodings plus a hex view, and can hand the raw bytes to the extraction
pipeline (signature scan) so recovered files surface automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from ...core import config
from ...core.util import bits_to_bytes, hex_dump, decode_text_variants, find_interesting, b64
from .loader import LoadedImage, load_image, channel_index


@dataclass
class LSBParams:
    channels: list[str] = field(default_factory=lambda: ["R", "G", "B"])
    bit_planes: list[int] = field(default_factory=lambda: [0])   # 0=LSB … 7=MSB
    traversal: Literal["row", "column"] = "row"                  # pixel order
    channel_mode: Literal["interleave", "sequential"] = "interleave"
    bit_order: Literal["msb", "lsb"] = "msb"                     # within output byte
    plane_order: Literal["ascending", "descending"] = "ascending"
    max_bytes: int = 1 << 20

    def normalise(self) -> "LSBParams":
        self.bit_planes = sorted({int(b) for b in self.bit_planes if 0 <= int(b) <= 7})
        if not self.bit_planes:
            self.bit_planes = [0]
        if self.plane_order == "descending":
            self.bit_planes = self.bit_planes[::-1]
        self.max_bytes = max(1, min(int(self.max_bytes), config.MAX_LSB_OUTPUT_BYTES))
        return self


def _collect_bits(loaded: LoadedImage, params: LSBParams) -> np.ndarray:
    arr = loaded.array
    if arr.dtype != np.uint8:
        arr = (arr.astype(np.uint32) & 0xFF).astype(np.uint8)

    # resolve channel indices
    idxs = []
    for ch in params.channels:
        try:
            idxs.append(channel_index(loaded, ch))
        except ValueError:
            continue
    if not idxs:
        raise ValueError(f"None of channels {params.channels} present in image {loaded.channels}")

    # traversal: flatten H x W per channel
    def flat(ch_idx: int) -> np.ndarray:
        plane = arr[:, :, ch_idx]
        if params.traversal == "column":
            plane = plane.T
        return plane.reshape(-1)

    # For each selected channel produce a (npix, nbitplanes) array of bits in
    # the chosen plane order.
    planes = params.bit_planes
    per_channel_bits = []
    for ci in idxs:
        samples = flat(ci).astype(np.uint8)
        # shape (npix, len(planes))
        stacked = np.stack([((samples >> p) & 1) for p in planes], axis=1)
        per_channel_bits.append(stacked)

    npix = per_channel_bits[0].shape[0]
    nplanes = len(planes)

    if params.channel_mode == "interleave":
        # order: pixel0 ch0 planes, pixel0 ch1 planes, ... pixel1 ch0 planes ...
        stack = np.stack(per_channel_bits, axis=1)  # (npix, nchan, nplanes)
        bits = stack.reshape(npix * len(idxs) * nplanes)
    else:  # sequential: all of ch0 then all of ch1 ...
        bits = np.concatenate([pc.reshape(-1) for pc in per_channel_bits])

    return bits.astype(np.uint8)


def extract(path: str | Path, params: LSBParams) -> dict:
    params = params.normalise()
    loaded = load_image(path)
    bits = _collect_bits(loaded, params)
    data = bits_to_bytes(bits, msb_first=(params.bit_order == "msb"))
    data = data[: params.max_bytes]

    preview = data[:4096]
    return {
        "params": {
            "channels": params.channels,
            "bit_planes": params.bit_planes,
            "traversal": params.traversal,
            "channel_mode": params.channel_mode,
            "bit_order": params.bit_order,
            "plane_order": params.plane_order,
        },
        "image": {
            "width": loaded.width,
            "height": loaded.height,
            "channels": loaded.channels,
            "mode": loaded.original_mode,
        },
        "total_bits": int(bits.size),
        "extracted_bytes": len(data),
        "hex": hex_dump(preview),
        "text": decode_text_variants(preview),
        "interesting": find_interesting(data),
        "base64": b64(data[: params.max_bytes]),
    }


def extract_raw(path: str | Path, params: LSBParams) -> bytes:
    params = params.normalise()
    loaded = load_image(path)
    bits = _collect_bits(loaded, params)
    data = bits_to_bytes(bits, msb_first=(params.bit_order == "msb"))
    return data[: params.max_bytes]
