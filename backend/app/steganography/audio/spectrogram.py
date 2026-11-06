"""Interactive spectrogram rendering.

Produces an STFT (or mel) spectrogram as a PNG, with fully configurable FFT
size, hop length, window, overlap, frequency scale (linear/log/mel), dynamic
range and colormap. Nothing is hardcoded — every parameter is exposed.

Hidden text/images in CTF audio usually appears as structure in the high
frequencies, so the renderer supports frequency cropping and a wide dynamic
range.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Literal, Optional

import numpy as np
from matplotlib import colormaps
from PIL import Image
from scipy.signal import get_window, stft as scipy_stft

from .loader import load_audio, slice_frames

_ALLOWED_WINDOWS = ("hann", "hamming", "blackman", "bartlett", "boxcar",
                    "blackmanharris", "flattop", "tukey")
_ALLOWED_CMAPS = ("viridis", "magma", "inferno", "plasma", "turbo", "gray", "jet")


def _colormap_rgb(norm: np.ndarray, cmap: str) -> np.ndarray:
    cmap = cmap if cmap in _ALLOWED_CMAPS else "viridis"
    lut = (colormaps[cmap](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)
    idx = np.clip((norm * 255).astype(np.int32), 0, 255)
    return lut[idx]


def compute_spectrogram(
    path: str | Path,
    *,
    channel: int = 0,
    n_fft: int = 1024,
    hop: Optional[int] = None,
    window: str = "hann",
    overlap: Optional[float] = None,     # 0..1, alternative to hop
    scale: Literal["linear", "log", "mel"] = "linear",
    f_min: float = 0.0,
    f_max: Optional[float] = None,
    top_db: float = 80.0,
    n_mels: int = 256,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> dict:
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    sr = a.sample_rate

    n_fft = int(max(32, min(n_fft, 16384)))
    if overlap is not None and hop is None:
        hop = max(1, int(n_fft * (1 - float(overlap))))
    if hop is None:
        hop = n_fft // 4
    hop = int(max(1, min(hop, n_fft)))
    win_name = window if window in _ALLOWED_WINDOWS else "hann"

    if scale == "mel":
        import librosa
        S = librosa.feature.melspectrogram(
            y=sig.astype(np.float32), sr=sr, n_fft=n_fft, hop_length=hop,
            win_length=n_fft, window=win_name, n_mels=int(max(16, min(n_mels, 512))),
            fmin=f_min, fmax=f_max or sr / 2,
        )
        power = S
        freqs = librosa.mel_frequencies(n_mels=power.shape[0], fmin=f_min, fmax=f_max or sr / 2)
        times = librosa.frames_to_time(np.arange(power.shape[1]), sr=sr, hop_length=hop)
    else:
        win = get_window(win_name, n_fft, fftbins=True)
        f, t, Z = scipy_stft(sig, fs=sr, window=win, nperseg=n_fft,
                             noverlap=n_fft - hop, boundary=None, padded=False)
        power = np.abs(Z) ** 2
        freqs = f
        times = t + (s / sr)

    # dB conversion with a top_db dynamic range
    ref = power.max() if power.size else 1.0
    db = 10.0 * np.log10(np.maximum(power, 1e-12) / max(ref, 1e-12))
    db = np.maximum(db, -abs(top_db))

    # frequency crop
    fmax = f_max if f_max else sr / 2
    fmask = (freqs >= f_min) & (freqs <= fmax)
    if fmask.sum() >= 2:
        db = db[fmask, :]
        freqs_c = freqs[fmask]
    else:
        freqs_c = freqs

    # log-frequency resampling for display (optional)
    display = db
    disp_freqs = freqs_c
    if scale == "log" and freqs_c.size > 2 and freqs_c[0] >= 0:
        lo = max(freqs_c[freqs_c > 0].min(), 1.0)
        hi = freqs_c.max()
        target = np.logspace(np.log10(lo), np.log10(hi), num=min(512, db.shape[0]))
        display = np.empty((target.size, db.shape[1]))
        for col in range(db.shape[1]):
            display[:, col] = np.interp(target, freqs_c, db[:, col])
        disp_freqs = target

    return {
        "db": display,
        "freqs": disp_freqs,
        "times": times,
        "sample_rate": sr,
        "n_fft": n_fft,
        "hop": hop,
        "window": win_name,
        "scale": scale,
        "top_db": top_db,
        "f_min": float(f_min),
        "f_max": float(fmax),
        "transformations": a.transformations,
    }


def render_png(spec: dict, cmap: str = "magma", max_width: int = 2000) -> bytes:
    db = spec["db"]
    if db.size == 0:
        raise ValueError("Empty spectrogram (signal too short for these parameters)")
    lo = db.min()
    hi = db.max()
    norm = (db - lo) / (hi - lo + 1e-12)
    rgb = _colormap_rgb(norm, cmap)           # (freq, time, 3)
    rgb = np.flipud(rgb)                       # low freq at bottom
    im = Image.fromarray(rgb, mode="RGB")
    if im.width > max_width:
        scale = max_width / im.width
        im = im.resize((max_width, max(1, int(im.height))), Image.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def spectrogram_image(path: str | Path, cmap: str = "magma", **kwargs) -> tuple[bytes, dict]:
    spec = compute_spectrogram(path, **kwargs)
    png = render_png(spec, cmap=cmap)
    meta = {
        "sample_rate": spec["sample_rate"],
        "n_fft": spec["n_fft"],
        "hop": spec["hop"],
        "window": spec["window"],
        "scale": spec["scale"],
        "top_db": spec["top_db"],
        "f_min": spec["f_min"],
        "f_max": spec["f_max"],
        "freq_bins": int(spec["db"].shape[0]),
        "time_frames": int(spec["db"].shape[1]),
        "time_start": float(spec["times"][0]) if len(spec["times"]) else 0.0,
        "time_end": float(spec["times"][-1]) if len(spec["times"]) else 0.0,
        "colormap": cmap,
        "transformations": spec["transformations"],
    }
    return png, meta
