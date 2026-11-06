"""Audio loading / decoding.

Two distinct representations are produced because they serve different jobs:

  * **Float samples** (``-1..1``, shape ``frames x channels``) for all DSP
    (waveform, spectrogram, FFT, phase/echo). Works for every format.
  * **Integer PCM samples** with their true bit width, ONLY for truly lossless
    PCM sources (WAV/FLAC/AIFF). This is what PCM-LSB steganography operates
    on. For lossy formats (MP3/OGG) there are no meaningful original sample
    bits, so ``is_lossless_pcm`` is False and the PCM-LSB engine refuses to
    pretend otherwise.

The original file is never modified. When a format needs transcoding to be
read we go through ffmpeg into a temp WAV and record that transformation.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from ...core import config, tools
from ...core.tools import run_tool

_LOSSLESS_SUBTYPES = ("PCM_S8", "PCM_U8", "PCM_16", "PCM_24", "PCM_32", "ALAC", "FLAC")


@dataclass
class LoadedAudio:
    float_samples: np.ndarray     # frames x channels, float64 in [-1, 1]
    sample_rate: int
    channels: int
    n_frames: int
    duration: float
    source_format: str
    subtype: Optional[str]
    is_lossless_pcm: bool
    int_samples: Optional[np.ndarray] = None   # frames x channels, integer
    sample_width_bits: Optional[int] = None
    transformations: list[str] = field(default_factory=list)

    def channel(self, i: int) -> np.ndarray:
        return self.float_samples[:, i]

    def mono(self) -> np.ndarray:
        return self.float_samples.mean(axis=1)


_INT_DTYPE = {"PCM_S8": np.int16, "PCM_U8": np.int16, "PCM_16": np.int16,
              "PCM_24": np.int32, "PCM_32": np.int32, "FLAC": np.int32, "ALAC": np.int32}
_WIDTH_BITS = {"PCM_S8": 8, "PCM_U8": 8, "PCM_16": 16, "PCM_24": 24, "PCM_32": 32,
               "FLAC": 24, "ALAC": 24}


def _duration_guard(n_frames: int, sr: int) -> None:
    if sr > 0 and n_frames / sr > config.MAX_AUDIO_SECONDS:
        raise ValueError(f"Audio longer than {config.MAX_AUDIO_SECONDS}s limit")


def load_audio(path: str | Path) -> LoadedAudio:
    path = str(path)
    transformations: list[str] = []

    # First try libsndfile directly (covers WAV/FLAC/OGG/AIFF).
    try:
        info = sf.info(path)
        _duration_guard(info.frames, info.samplerate)
        fmt = info.format
        subtype = info.subtype
        is_pcm = any(subtype.startswith(s) or subtype == s for s in _LOSSLESS_SUBTYPES) \
            and fmt in ("WAV", "FLAC", "AIFF", "AU", "W64")
        data, sr = sf.read(path, dtype="float64", always_2d=True)
        loaded = LoadedAudio(
            float_samples=data, sample_rate=sr, channels=data.shape[1],
            n_frames=data.shape[0], duration=data.shape[0] / sr if sr else 0.0,
            source_format=fmt.lower(), subtype=subtype, is_lossless_pcm=is_pcm,
            transformations=transformations,
        )
        if is_pcm:
            int_dtype = _INT_DTYPE.get(subtype, np.int32)
            ints, _ = sf.read(path, dtype="int32" if int_dtype is np.int32 else "int16",
                              always_2d=True)
            loaded.int_samples = ints
            loaded.sample_width_bits = _WIDTH_BITS.get(subtype, 16)
        return loaded
    except Exception:
        pass

    # Fall back to ffmpeg -> temp WAV (MP3, exotic containers). Lossy => no PCM.
    return _load_via_ffmpeg(path, transformations)


def _load_via_ffmpeg(path: str, transformations: list[str]) -> LoadedAudio:
    if not tools.available("ffmpeg"):
        raise ValueError("Cannot decode this audio format: ffmpeg is not installed")
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "decoded.wav")
        res = run_tool("ffmpeg", ["-v", "error", "-i", path, "-c:a", "pcm_s16le", wav],
                       timeout=300)
        if not res.ok or not os.path.exists(wav):
            raise ValueError(f"ffmpeg failed to decode audio: {res.stderr[:300]}")
        transformations.append("Decoded to 16-bit PCM WAV via ffmpeg (lossy source: "
                                "sample LSBs are decoder output, not original hidden bits)")
        data, sr = sf.read(wav, dtype="float64", always_2d=True)
        _duration_guard(data.shape[0], sr)
        ext = Path(path).suffix.lower().lstrip(".") or "unknown"
        return LoadedAudio(
            float_samples=data, sample_rate=sr, channels=data.shape[1],
            n_frames=data.shape[0], duration=data.shape[0] / sr if sr else 0.0,
            source_format=ext, subtype="decoded-pcm_s16le", is_lossless_pcm=False,
            transformations=transformations,
        )


def slice_frames(sr: int, start: Optional[float], end: Optional[float], n_frames: int) -> tuple[int, int]:
    s = 0 if start is None else max(0, int(start * sr))
    e = n_frames if end is None else min(n_frames, int(end * sr))
    if e <= s:
        e = n_frames
    return s, e
