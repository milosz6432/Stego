"""Advanced audio steganography analysis.

These are *detection heuristics and visualisations*, clearly distinguished
from exact extraction. Each returns a description, the parameters used, and a
result the UI can plot. We do not claim to reliably detect every scheme.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .loader import load_audio, slice_frames


def phase_analysis(path: str | Path, *, n_fft: int = 1024, channel: int = 0,
                   start: Optional[float] = None, end: Optional[float] = None) -> dict:
    """Phase-coding hides data in the absolute phase of early frames. We report
    the phase of the first analysis frame across frequency bins; a staircase /
    quantised pattern (e.g. phases clustered at 0/pi) is suspicious."""
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    if sig.size < n_fft:
        raise ValueError("Segment shorter than FFT size")
    frame = sig[:n_fft] * np.hanning(n_fft)
    spec = np.fft.rfft(frame)
    phase = np.angle(spec)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / a.sample_rate)
    # quantisation cue: how concentrated phases are near 0 / ±pi/2 / ±pi
    hist, _ = np.histogram(phase, bins=36, range=(-np.pi, np.pi))
    concentration = float(hist.max() / max(hist.sum(), 1))
    return {
        "method": "phase_coding",
        "description": "Phase of the first STFT frame; quantised phase clusters "
                       "suggest phase-coding steganography.",
        "parameters": {"n_fft": n_fft, "channel": ch},
        "freqs": freqs.tolist(),
        "phase": [round(float(p), 4) for p in phase],
        "phase_concentration": round(concentration, 3),
        "suspicious": concentration > 0.12,
    }


def echo_analysis(path: str | Path, *, channel: int = 0, max_delay_ms: float = 50.0,
                  start: Optional[float] = None, end: Optional[float] = None) -> dict:
    """Echo hiding encodes bits as short echoes at one of two delays. We take
    the cepstrum (IFFT of log-magnitude spectrum); strong peaks at small
    quefrencies indicate echoes."""
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    if sig.size < 256:
        raise ValueError("Segment too short")
    spectrum = np.fft.rfft(sig * np.hanning(sig.size))
    log_mag = np.log(np.abs(spectrum) + 1e-12)
    cepstrum = np.fft.irfft(log_mag)
    max_lag = int(a.sample_rate * max_delay_ms / 1000)
    cep = np.abs(cepstrum[1:max_lag])
    lags_ms = (np.arange(1, max_lag) / a.sample_rate) * 1000
    peak_idx = int(np.argmax(cep)) if cep.size else 0
    return {
        "method": "echo_hiding",
        "description": "Cepstral peaks at short quefrencies indicate hidden echoes.",
        "parameters": {"channel": ch, "max_delay_ms": max_delay_ms},
        "lags_ms": [round(float(x), 3) for x in lags_ms],
        "cepstrum": [round(float(x), 5) for x in cep],
        "dominant_echo_ms": round(float(lags_ms[peak_idx]), 3) if cep.size else None,
        "dominant_strength": round(float(cep[peak_idx]), 5) if cep.size else None,
    }


def stereo_analysis(path: str | Path, *, start: Optional[float] = None,
                    end: Optional[float] = None) -> dict:
    """Stereo channel difference, correlation and L-R residual (data is often
    hidden only in one channel or in the inter-channel difference)."""
    a = load_audio(path)
    if a.channels < 2:
        return {"channels": a.channels, "note": "Mono audio — no stereo analysis"}
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    left = a.float_samples[s:e, 0]
    right = a.float_samples[s:e, 1]
    corr = float(np.corrcoef(left, right)[0, 1]) if left.size > 1 else 0.0
    diff = left - right
    return {
        "channels": a.channels,
        "correlation": round(corr, 5),
        "diff_rms": round(float(np.sqrt(np.mean(diff ** 2))), 6),
        "diff_peak": round(float(np.max(np.abs(diff))) if diff.size else 0.0, 6),
        "identical_channels": bool(np.array_equal(left, right)),
        "note": "Very high correlation with a non-zero difference RMS can mean a "
                "payload lives in the L-R residual.",
    }


def zero_crossing(path: str | Path, *, channel: int = 0, window_ms: float = 20.0,
                  start: Optional[float] = None, end: Optional[float] = None) -> dict:
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    win = max(1, int(a.sample_rate * window_ms / 1000))
    nwin = sig.size // win
    if nwin == 0:
        raise ValueError("Segment too short")
    blocks = sig[:nwin * win].reshape(nwin, win)
    zcr = np.mean(np.abs(np.diff(np.sign(blocks), axis=1)) > 0, axis=1)
    times = np.arange(nwin) * window_ms / 1000 + s / a.sample_rate
    return {
        "method": "zero_crossing_rate",
        "parameters": {"channel": ch, "window_ms": window_ms},
        "times": [round(float(t), 4) for t in times],
        "zcr": [round(float(z), 4) for z in zcr],
    }


def pattern_scan(path: str | Path, *, channel: int = 0) -> dict:
    """Look for repeated short blocks in the sample stream (spread-spectrum /
    repetition encoding) via autocorrelation of the LSB bit sequence."""
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    if a.is_lossless_pcm and a.int_samples is not None:
        bits = (a.int_samples[:, ch] & 1).astype(np.float64)
        source = "pcm_lsb"
    else:
        bits = (a.float_samples[:, ch] > 0).astype(np.float64)
        source = "sign_bits (lossy source)"
    bits = bits[: min(bits.size, 200000)]
    bits = bits - bits.mean()
    if bits.size < 16:
        raise ValueError("Too few samples")
    ac = np.correlate(bits, bits, mode="full")[bits.size - 1:]
    ac = ac / (ac[0] + 1e-12)
    # find strong non-zero-lag peaks
    lag_region = ac[1:min(ac.size, 5000)]
    peaks = []
    if lag_region.size:
        thr = 0.3
        idx = np.where(lag_region > thr)[0] + 1
        for i in idx[:20]:
            peaks.append({"lag_samples": int(i), "strength": round(float(ac[i]), 3)})
    return {
        "method": "repetition_autocorrelation",
        "source": source,
        "parameters": {"channel": ch},
        "autocorr_peaks": peaks,
        "note": "Strong peaks at a fixed lag indicate a repeating hidden pattern.",
    }
