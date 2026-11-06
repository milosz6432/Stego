"""Export a time segment of audio as a new WAV (for listening / re-analysis).

Writes lossless 16/24-bit PCM so the exported segment itself can be run back
through the PCM-LSB engine. The original file is untouched.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from .loader import load_audio, slice_frames


def export_segment(path: str | Path, start: Optional[float], end: Optional[float],
                   *, channel: Optional[int] = None) -> tuple[bytes, dict]:
    a = load_audio(path)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    data = a.float_samples[s:e]
    if channel is not None and 0 <= channel < a.channels:
        data = data[:, channel:channel + 1]
    buf = io.BytesIO()
    subtype = "PCM_24" if (a.sample_width_bits or 16) > 16 else "PCM_16"
    sf.write(buf, data, a.sample_rate, format="WAV", subtype=subtype)
    meta = {
        "sample_rate": a.sample_rate,
        "channels": data.shape[1],
        "frames": data.shape[0],
        "start_time": s / a.sample_rate,
        "end_time": e / a.sample_rate,
        "subtype": subtype,
    }
    return buf.getvalue(), meta
