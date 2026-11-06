"""PCM sample LSB steganography engine.

Operates on the *integer* samples of a lossless PCM source. A payload may be
hidden in any combination of:

  * bit position(s) within each sample (0 = LSB … up to sample width - 1),
  * channel selection and order,
  * channel interleave vs channel-sequential layout,
  * output bit order (MSB-first / LSB-first within a byte),
  * endianness interpretation of multi-byte samples (handled by reading the
    container correctly; the integer array already holds native values).

For lossy sources (MP3/OGG) this engine refuses to run, because decoded
sample LSBs are decoder output, not hidden bits — faking it would be
misleading. Use the spectrogram/phase tools on those instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from ...core import config
from ...core.util import bits_to_bytes, hex_dump, decode_text_variants, find_interesting, b64
from .loader import load_audio


@dataclass
class PCMParams:
    channels: list[int] = field(default_factory=lambda: [0])
    bit_planes: list[int] = field(default_factory=lambda: [0])
    channel_mode: Literal["interleave", "sequential"] = "interleave"
    bit_order: Literal["msb", "lsb"] = "msb"
    max_bytes: int = 1 << 20

    def normalise(self, width_bits: int) -> "PCMParams":
        self.bit_planes = sorted({int(b) for b in self.bit_planes if 0 <= int(b) < width_bits})
        if not self.bit_planes:
            self.bit_planes = [0]
        self.max_bytes = max(1, min(int(self.max_bytes), config.MAX_LSB_OUTPUT_BYTES))
        return self


class NotLosslessPCM(ValueError):
    pass


def _collect_bits(int_samples: np.ndarray, params: PCMParams) -> np.ndarray:
    # int_samples shape: frames x channels (signed). Work on the unsigned bit
    # pattern so negative samples' two's-complement bits extract correctly.
    nch = int_samples.shape[1]
    chans = [c for c in params.channels if 0 <= c < nch] or [0]
    planes = params.bit_planes

    per_channel = []
    for c in chans:
        samples = int_samples[:, c].astype(np.int64)
        # mask to the extraction planes using the raw integer bits
        stacked = np.stack([((samples >> p) & 1).astype(np.uint8) for p in planes], axis=1)
        per_channel.append(stacked)

    nframes = per_channel[0].shape[0]
    nplanes = len(planes)
    if params.channel_mode == "interleave":
        stack = np.stack(per_channel, axis=1)       # frames x nchan x nplanes
        bits = stack.reshape(nframes * len(chans) * nplanes)
    else:
        bits = np.concatenate([pc.reshape(-1) for pc in per_channel])
    return bits.astype(np.uint8)


def extract(path: str | Path, params: PCMParams) -> dict:
    a = load_audio(path)
    if not a.is_lossless_pcm or a.int_samples is None:
        raise NotLosslessPCM(
            f"Source '{a.source_format}' is not lossless PCM; sample-LSB extraction "
            "is not meaningful on decoded lossy audio. Transformations: "
            + "; ".join(a.transformations or ["(none)"])
        )
    params = params.normalise(a.sample_width_bits or 16)
    bits = _collect_bits(a.int_samples, params)
    data = bits_to_bytes(bits, msb_first=(params.bit_order == "msb"))[: params.max_bytes]
    preview = data[:4096]
    return {
        "params": {
            "channels": params.channels, "bit_planes": params.bit_planes,
            "channel_mode": params.channel_mode, "bit_order": params.bit_order,
        },
        "audio": {
            "sample_rate": a.sample_rate, "channels": a.channels,
            "sample_width_bits": a.sample_width_bits, "format": a.source_format,
            "subtype": a.subtype,
        },
        "total_bits": int(bits.size),
        "extracted_bytes": len(data),
        "hex": hex_dump(preview),
        "text": decode_text_variants(preview),
        "interesting": find_interesting(data),
        "base64": b64(data),
        "signatures": _quick_signatures(data),
    }


def extract_raw(path: str | Path, params: PCMParams) -> bytes:
    a = load_audio(path)
    if not a.is_lossless_pcm or a.int_samples is None:
        raise NotLosslessPCM("Not a lossless PCM source")
    params = params.normalise(a.sample_width_bits or 16)
    bits = _collect_bits(a.int_samples, params)
    return bits_to_bytes(bits, msb_first=(params.bit_order == "msb"))[: params.max_bytes]


_SIGS = [
    (b"PK\x03\x04", "zip"), (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpeg"),
    (b"GIF8", "gif"), (b"%PDF", "pdf"), (b"7z\xbc\xaf", "7z"),
    (b"Rar!", "rar"), (b"\x1f\x8b", "gzip"), (b"BZh", "bzip2"), (b"ID3", "mp3"),
    (b"RIFF", "riff"), (b"OggS", "ogg"), (b"fLaC", "flac"),
]


def _quick_signatures(data: bytes) -> list[dict]:
    found = []
    for sig, name in _SIGS:
        off = data.find(sig)
        if off != -1 and off < 4096:
            found.append({"format": name, "offset": off})
    return found
