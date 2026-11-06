"""DTMF (touch-tone) decoder using the Goertzel algorithm.

Slides a window over the signal, runs Goertzel at the 8 DTMF frequencies, and
emits a digit when exactly one low-group and one high-group tone dominate.
Consecutive identical detections are collapsed into one keypress.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .loader import load_audio, slice_frames

_LOW = [697, 770, 852, 941]
_HIGH = [1209, 1336, 1477, 1633]
_KEYS = [
    ["1", "2", "3", "A"],
    ["4", "5", "6", "B"],
    ["7", "8", "9", "C"],
    ["*", "0", "#", "D"],
]


def _goertzel(samples: np.ndarray, sr: int, freq: float) -> float:
    n = samples.size
    k = int(0.5 + (n * freq) / sr)
    w = (2 * np.pi * k) / n
    coeff = 2 * np.cos(w)
    s_prev = s_prev2 = 0.0
    for x in samples:
        s = x + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
    power = s_prev2 ** 2 + s_prev ** 2 - coeff * s_prev * s_prev2
    return float(power)


def decode(path: str | Path, *, channel: int = 0, win_ms: float = 40.0,
           hop_ms: float = 20.0, start: Optional[float] = None,
           end: Optional[float] = None) -> dict:
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    sr = a.sample_rate
    win = max(64, int(sr * win_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))

    detections = []
    for pos in range(0, max(0, sig.size - win), hop):
        block = sig[pos:pos + win]
        if np.sqrt(np.mean(block ** 2)) < 1e-3:
            detections.append(None)
            continue
        low_p = [_goertzel(block, sr, f) for f in _LOW]
        high_p = [_goertzel(block, sr, f) for f in _HIGH]
        li = int(np.argmax(low_p))
        hi = int(np.argmax(high_p))
        # require dominance over the rest of the group
        low_ok = low_p[li] > 4 * (sum(low_p) - low_p[li] + 1e-9) / 3
        high_ok = high_p[hi] > 4 * (sum(high_p) - high_p[hi] + 1e-9) / 3
        detections.append(_KEYS[li][hi] if (low_ok and high_ok) else None)

    # collapse runs
    digits = []
    prev = None
    run = 0
    for d in detections + [None]:
        if d == prev:
            run += 1
        else:
            if prev is not None and run >= 2:
                digits.append(prev)
            prev = d
            run = 1
    return {
        "method": "dtmf_goertzel",
        "parameters": {"channel": ch, "win_ms": win_ms, "hop_ms": hop_ms},
        "sequence": "".join(digits),
        "digits": digits,
        "count": len(digits),
    }
