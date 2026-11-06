"""Shared pytest fixtures and synthetic steganography file generators.

Every generator embeds a *known* payload so tests can assert exact recovery.
The data directory is redirected to a temp path before any app import so tests
never touch real uploads.
"""
import io
import os
import tempfile
import zipfile
from pathlib import Path

# Redirect all storage to an isolated temp dir BEFORE importing the app.
_TMP_DATA = tempfile.mkdtemp(prefix="stego_test_")
os.environ["STEGO_DATA_DIR"] = _TMP_DATA

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import soundfile as sf  # noqa: E402
from PIL import Image  # noqa: E402


# ---- image helpers ----------------------------------------------------------
def embed_lsb_png(path, message: bytes, channel: str = "R", size=(64, 64), seed=0):
    """Embed *message* in one channel's LSB (plane 0), row-major, MSB-first,
    sequential — matching LSBParams(channels=[channel], channel_mode='sequential',
    bit_planes=[0], bit_order='msb', traversal='row')."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    bits = np.unpackbits(np.frombuffer(message, dtype=np.uint8))  # MSB-first
    ci = {"R": 0, "G": 1, "B": 2}[channel]
    flat = arr[:, :, ci].reshape(-1)
    assert bits.size <= flat.size, "message too large for cover"
    flat[: bits.size] = (flat[: bits.size] & 0xFE) | bits
    arr[:, :, ci] = flat.reshape(size[1], size[0])
    Image.fromarray(arr, "RGB").save(path)
    return path


def make_png_with_appended_zip(path, inner_name: str, inner_content: bytes, flag: bytes):
    rng = np.random.default_rng(1)
    img = Image.fromarray(rng.integers(0, 256, (48, 48, 3), dtype=np.uint8), "RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr(inner_name, inner_content + flag)
    Path(path).write_bytes(png + zbuf.getvalue())
    return path


def make_bitplane_image(path, size=(80, 80)):
    """Image whose blue LSB plane carries a visible structured pattern."""
    rng = np.random.default_rng(2)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    # write a checkerboard into B plane 0
    yy, xx = np.mgrid[0 : size[1], 0 : size[0]]
    pattern = ((xx // 4 + yy // 4) % 2).astype(np.uint8)
    arr[:, :, 2] = (arr[:, :, 2] & 0xFE) | pattern
    Image.fromarray(arr, "RGB").save(path)
    return path


# ---- audio helpers ----------------------------------------------------------
def embed_pcm_lsb_wav(path, message: bytes, sr=44100, channel=0, channels=1, seed=0):
    """Embed message in channel's sample LSB (plane 0), MSB-first interleave."""
    rng = np.random.default_rng(seed)
    n = max(sr, len(message) * 8 + 100)
    data = (rng.integers(-8000, 8000, (n, channels))).astype(np.int16)
    bits = np.unpackbits(np.frombuffer(message, dtype=np.uint8))
    col = data[:, channel]
    col[: bits.size] = (col[: bits.size] & ~1) | bits
    data[:, channel] = col
    sf.write(path, data, sr, subtype="PCM_16")
    return path


def embed_stereo_payloads(path, left_msg: bytes, right_msg: bytes, sr=44100, seed=3):
    rng = np.random.default_rng(seed)
    n = max(sr, (max(len(left_msg), len(right_msg)) * 8 + 100))
    data = rng.integers(-8000, 8000, (n, 2)).astype(np.int16)
    for ch, msg in ((0, left_msg), (1, right_msg)):
        bits = np.unpackbits(np.frombuffer(msg, dtype=np.uint8))
        col = data[:, ch]
        col[: bits.size] = (col[: bits.size] & ~1) | bits
        data[:, ch] = col
    sf.write(path, data, sr, subtype="PCM_16")
    return path


def make_dtmf_wav(path, digits="123", sr=8000):
    low = {"1": 697, "2": 697, "3": 697, "4": 770, "5": 770, "6": 770,
           "7": 852, "8": 852, "9": 852, "0": 941}
    high = {"1": 1209, "2": 1336, "3": 1477, "4": 1209, "5": 1336, "6": 1477,
            "7": 1209, "8": 1336, "9": 1477, "0": 1336}
    parts = []
    for d in digits:
        t = np.arange(int(sr * 0.2)) / sr
        parts.append(0.5 * (np.sin(2 * np.pi * low[d] * t) + np.sin(2 * np.pi * high[d] * t)))
        parts.append(np.zeros(int(sr * 0.1)))
    sig = np.concatenate(parts).astype(np.float32)
    sf.write(path, sig, sr, subtype="PCM_16")
    return path


def make_morse_wav(path, text="SOS", sr=8000, unit=0.08, freq=700):
    table = {"S": "...", "O": "---", "A": ".-", "E": ".", "T": "-"}
    def tone(units):
        t = np.arange(int(sr * unit * units)) / sr
        return 0.6 * np.sin(2 * np.pi * freq * t)
    def gap(units):
        return np.zeros(int(sr * unit * units))
    parts = []
    letters = [table[c] for c in text]
    for li, code in enumerate(letters):
        for si, sym in enumerate(code):
            parts.append(tone(1 if sym == "." else 3))
            if si < len(code) - 1:
                parts.append(gap(1))
        if li < len(letters) - 1:
            parts.append(gap(3))
    sig = np.concatenate(parts).astype(np.float32)
    sf.write(path, sig, sr, subtype="PCM_16")
    return path


# ---- fixtures ---------------------------------------------------------------
@pytest.fixture
def workdir(tmp_path):
    return tmp_path


@pytest.fixture
def png_lsb(tmp_path):
    p = tmp_path / "lsb.png"
    embed_lsb_png(p, b"FLAG{image_lsb_recovered}\x00end")
    return p


@pytest.fixture
def png_appended_zip(tmp_path):
    p = tmp_path / "appended.png"
    make_png_with_appended_zip(p, "secret.txt", b"", b"FLAG{zip_in_png}")
    return p


@pytest.fixture
def wav_pcm(tmp_path):
    p = tmp_path / "pcm.wav"
    embed_pcm_lsb_wav(p, b"FLAG{pcm_lsb_recovered}\x00end")
    return p


@pytest.fixture
def wav_stereo(tmp_path):
    p = tmp_path / "stereo.wav"
    embed_stereo_payloads(p, b"LEFT{channel_zero}", b"RIGHT{channel_one}")
    return p


@pytest.fixture
def dtmf_wav(tmp_path):
    p = tmp_path / "dtmf.wav"
    make_dtmf_wav(p, "19073")
    return p


@pytest.fixture
def morse_wav(tmp_path):
    p = tmp_path / "morse.wav"
    make_morse_wav(p, "SOS")
    return p


@pytest.fixture
def bitplane_png(tmp_path):
    p = tmp_path / "bitplane.png"
    make_bitplane_image(p)
    return p
