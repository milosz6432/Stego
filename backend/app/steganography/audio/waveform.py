"""Waveform visualisation data + amplitude statistics.

Returns downsampled min/max peak envelopes (so the frontend can draw a full
waveform without transferring every sample), RMS, peak, silence regions and
basic anomaly cues. Operates on an optional time range.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .loader import LoadedAudio, load_audio, slice_frames


def _peaks(signal: np.ndarray, buckets: int) -> list[list[float]]:
    n = signal.size
    if n == 0:
        return []
    buckets = max(1, min(buckets, n))
    # pad to a multiple of bucket size
    step = int(np.ceil(n / buckets))
    pad = step * buckets - n
    if pad:
        signal = np.concatenate([signal, np.zeros(pad)])
    blocks = signal.reshape(buckets, step)
    mins = blocks.min(axis=1)
    maxs = blocks.max(axis=1)
    return [[round(float(lo), 5), round(float(hi), 5)] for lo, hi in zip(mins, maxs)]


def waveform(path: str | Path, *, buckets: int = 2000,
             start: Optional[float] = None, end: Optional[float] = None) -> dict:
    a = load_audio(path)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    out_channels = []
    for ch in range(a.channels):
        sig = a.float_samples[s:e, ch]
        out_channels.append(_peaks(sig, buckets))
    return {
        "sample_rate": a.sample_rate,
        "channels": a.channels,
        "duration": a.duration,
        "range": {"start_frame": s, "end_frame": e,
                  "start_time": s / a.sample_rate, "end_time": e / a.sample_rate},
        "buckets": buckets,
        "peaks": out_channels,
        "transformations": a.transformations,
        "is_lossless_pcm": a.is_lossless_pcm,
    }


def statistics(path: str | Path, *, start: Optional[float] = None,
               end: Optional[float] = None, silence_db: float = -50.0) -> dict:
    a = load_audio(path)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    stats = []
    for ch in range(a.channels):
        sig = a.float_samples[s:e, ch]
        if sig.size == 0:
            continue
        rms = float(np.sqrt(np.mean(sig ** 2)))
        peak = float(np.max(np.abs(sig)))
        crest = float(peak / rms) if rms > 0 else 0.0
        zc = int(np.sum(np.abs(np.diff(np.sign(sig))) > 0))
        stats.append({
            "channel": ch,
            "rms": round(rms, 6),
            "rms_db": round(20 * np.log10(rms + 1e-12), 2),
            "peak": round(peak, 6),
            "peak_db": round(20 * np.log10(peak + 1e-12), 2),
            "crest_factor": round(crest, 3),
            "zero_crossings": zc,
            "dc_offset": round(float(sig.mean()), 6),
        })
    # silence detection on mono mix
    mono = a.float_samples[s:e].mean(axis=1)
    silence = _silence_regions(mono, a.sample_rate, silence_db, offset=s)
    return {
        "sample_rate": a.sample_rate,
        "channels": a.channels,
        "per_channel": stats,
        "silence_regions": silence,
        "transformations": a.transformations,
    }


def _silence_regions(mono: np.ndarray, sr: int, thr_db: float, offset: int,
                     win_ms: float = 20.0) -> list[dict]:
    if mono.size == 0:
        return []
    win = max(1, int(sr * win_ms / 1000))
    thr = 10 ** (thr_db / 20.0)
    n_windows = mono.size // win
    if n_windows == 0:
        return []
    blocks = mono[:n_windows * win].reshape(n_windows, win)
    rms = np.sqrt(np.mean(blocks ** 2, axis=1))
    silent = rms < thr
    regions = []
    i = 0
    while i < n_windows:
        if silent[i]:
            j = i
            while j < n_windows and silent[j]:
                j += 1
            start_f = offset + i * win
            end_f = offset + j * win
            if (end_f - start_f) / sr >= 0.05:  # ignore <50ms
                regions.append({"start": round(start_f / sr, 3), "end": round(end_f / sr, 3)})
            i = j
        else:
            i += 1
    return regions[:200]
