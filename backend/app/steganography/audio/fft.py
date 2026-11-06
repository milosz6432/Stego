"""FFT / frequency-domain analysis.

Computes the magnitude spectrum of a (windowed) segment, finds peak
frequencies, estimates harmonic structure, and compares channels. Returns
downsampled arrays suitable for Plotly plus numeric peak tables.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from scipy.signal import get_window

from .loader import load_audio, slice_frames


def _downsample_xy(x: np.ndarray, y: np.ndarray, points: int) -> tuple[list, list]:
    if x.size <= points:
        return x.tolist(), y.tolist()
    idx = np.linspace(0, x.size - 1, points).astype(int)
    return x[idx].tolist(), y[idx].tolist()


def spectrum(path: str | Path, *, channel: int = 0, start: Optional[float] = None,
             end: Optional[float] = None, window: str = "hann",
             points: int = 4000) -> dict:
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    if sig.size < 16:
        raise ValueError("Segment too short for FFT")
    win = get_window(window if window else "hann", sig.size, fftbins=True)
    spec = np.fft.rfft(sig * win)
    mag = np.abs(spec)
    freqs = np.fft.rfftfreq(sig.size, d=1.0 / a.sample_rate)
    mag_db = 20 * np.log10(mag + 1e-12)

    # peak detection
    peaks = _find_peaks(freqs, mag, a.sample_rate)
    fx, fy = _downsample_xy(freqs, mag_db, points)
    return {
        "sample_rate": a.sample_rate,
        "channel": ch,
        "n_samples": int(sig.size),
        "freqs": fx,
        "magnitude_db": [round(v, 3) for v in fy],
        "peaks": peaks,
        "harmonics": _harmonics(peaks),
        "transformations": a.transformations,
    }


def _find_peaks(freqs: np.ndarray, mag: np.ndarray, sr: int, top: int = 20) -> list[dict]:
    if mag.size < 3:
        return []
    # local maxima
    is_peak = (mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:])
    idx = np.where(is_peak)[0] + 1
    if idx.size == 0:
        return []
    order = idx[np.argsort(mag[idx])[::-1]][:top]
    peak_max = mag.max() + 1e-12
    out = []
    for i in sorted(order):
        out.append({
            "frequency": round(float(freqs[i]), 2),
            "magnitude": round(float(mag[i]), 4),
            "relative_db": round(float(20 * np.log10(mag[i] / peak_max)), 2),
        })
    return out


def _harmonics(peaks: list[dict], tol: float = 0.03) -> list[dict]:
    if not peaks:
        return []
    fundamental = min(p["frequency"] for p in peaks if p["frequency"] > 0) if \
        any(p["frequency"] > 0 for p in peaks) else 0
    harmonics = []
    if fundamental > 0:
        for p in peaks:
            ratio = p["frequency"] / fundamental
            nearest = round(ratio)
            if nearest >= 1 and abs(ratio - nearest) <= tol:
                harmonics.append({"frequency": p["frequency"], "harmonic_number": nearest})
    return harmonics


def channel_comparison(path: str | Path, *, start: Optional[float] = None,
                       end: Optional[float] = None) -> dict:
    a = load_audio(path)
    if a.channels < 2:
        return {"channels": a.channels, "note": "Mono audio — no channel comparison"}
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    out = {"channels": a.channels, "peaks": {}}
    for ch in range(a.channels):
        sig = a.float_samples[s:e, ch]
        if sig.size < 16:
            continue
        spec = np.abs(np.fft.rfft(sig))
        freqs = np.fft.rfftfreq(sig.size, d=1.0 / a.sample_rate)
        out["peaks"][ch] = _find_peaks(freqs, spec, a.sample_rate, top=10)
    return out
