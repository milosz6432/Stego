"""SSTV (Slow-Scan TV) detection.

Full SSTV image demodulation (Martin/Scottie/Robot modes) is involved and
mode-specific. Rather than fake a decode, this module does what can be done
reliably: detect the presence of an SSTV VIS (Vertical Interval Signalling)
header and identify the mode from the VIS code. It reports clearly that full
image reconstruction is not implemented.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .loader import load_audio

# VIS code -> mode name (subset of common modes)
_VIS_MODES = {
    44: "Martin M1", 40: "Martin M2", 60: "Scottie S1", 56: "Scottie S2",
    76: "Scottie DX", 8: "Robot 36", 12: "Robot 72", 2: "Robot 24",
}


def _tone_freq(block: np.ndarray, sr: int) -> float:
    if block.size < 16:
        return 0.0
    spec = np.abs(np.fft.rfft(block * np.hanning(block.size)))
    freqs = np.fft.rfftfreq(block.size, d=1.0 / sr)
    return float(freqs[int(np.argmax(spec))])


def detect(path: str | Path) -> dict:
    a = load_audio(path)
    sig = a.float_samples[:, 0]
    sr = a.sample_rate
    # The VIS header starts with a 300 ms leader at 1900 Hz, a 10 ms 1200 Hz
    # break, another 300 ms 1900 Hz, then a 30 ms 1200 Hz start bit and 8 VIS
    # bits (1100 Hz = 1, 1300 Hz = 0) of 30 ms each.
    found = []
    leader_len = int(0.3 * sr)
    if sig.size < leader_len * 2:
        return {"method": "sstv_vis_detect", "detected": False,
                "note": "Signal too short to contain an SSTV header."}

    # scan first 5 seconds for a 1900 Hz leader
    scan_end = min(sig.size - leader_len, int(5 * sr))
    step = int(0.05 * sr)
    for pos in range(0, max(1, scan_end), step):
        f = _tone_freq(sig[pos:pos + leader_len], sr)
        if 1850 <= f <= 1950:
            # try to read VIS bits after the leader + break + leader + start bit
            bit_dur = int(0.03 * sr)
            base = pos + leader_len + int(0.01 * sr) + leader_len + bit_dur
            if base + 8 * bit_dur > sig.size:
                continue
            bits = []
            for b in range(8):
                bf = _tone_freq(sig[base + b * bit_dur:base + (b + 1) * bit_dur], sr)
                bits.append(1 if bf < 1200 else 0)  # 1100Hz=1, 1300Hz=0
            vis = sum(bit << i for i, bit in enumerate(bits[:7]))  # LSB first, 7 data bits
            found.append({"offset_s": round(pos / sr, 3), "vis_code": vis,
                          "mode": _VIS_MODES.get(vis, f"Unknown (VIS {vis})")})
            break

    return {
        "method": "sstv_vis_detect",
        "detected": bool(found),
        "headers": found,
        "note": "VIS header detection only. Full SSTV image demodulation is not "
                "implemented; use a dedicated SSTV decoder (e.g. QSSTV) on the "
                "exported segment for the actual picture.",
    }
