"""Shared analysis utilities used across stego modules."""
from __future__ import annotations

import base64
import math
import re
from typing import Optional

import numpy as np


def bits_to_bytes(bits: np.ndarray, msb_first: bool = True) -> bytes:
    """Pack a 1-D array of 0/1 into bytes. Trailing partial byte is dropped."""
    bits = np.asarray(bits, dtype=np.uint8).ravel() & 1
    n = (bits.size // 8) * 8
    if n == 0:
        return b""
    bits = bits[:n].reshape(-1, 8)
    if not msb_first:
        bits = bits[:, ::-1]
    weights = (1 << np.arange(7, -1, -1)).astype(np.uint16)
    vals = (bits * weights).sum(axis=1).astype(np.uint8)
    return vals.tobytes()


def hex_dump(data: bytes, offset: int = 0, length: Optional[int] = None, width: int = 16) -> list[dict]:
    """Return rows suitable for a hex viewer: {offset, hex, ascii}."""
    if length is not None:
        data = data[:length]
    rows = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_pairs = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        rows.append({"offset": offset + i, "hex": hex_pairs, "ascii": ascii_part})
    return rows


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


_PRINTABLE = set(range(32, 127)) | {9, 10, 13}


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    good = sum(1 for b in data if b in _PRINTABLE)
    return good / len(data)


def shannon_entropy(data: bytes) -> float:
    """Bits/byte entropy (0..8)."""
    if not data:
        return 0.0
    arr = np.frombuffer(data, dtype=np.uint8)
    counts = np.bincount(arr, minlength=256).astype(np.float64)
    p = counts / counts.sum()
    nz = p[p > 0]
    return float(-(nz * np.log2(nz)).sum())


# Regexes for "interesting" text often seen in CTF flags / payloads.
# The prefix must start with a letter and the braces must contain only
# printable ASCII — this avoids matching random binary that happens to carry a
# stray "{...}". Common CTF forms: flag{...}, CTF{...}, picoCTF{...}, etc.
_FLAG_RE = re.compile(rb"[A-Za-z][A-Za-z0-9_]{1,29}\{[\x20-\x7e]{2,200}\}")
_URL_RE = re.compile(rb"https?://[^\s\"'<>]{4,200}")
_B64_RE = re.compile(rb"(?:[A-Za-z0-9+/]{20,}={0,2})")


def find_text_strings(data: bytes, min_len: int = 4, max_results: int = 200) -> list[dict]:
    """Extract printable ASCII runs (classic `strings`)."""
    out = []
    cur = bytearray()
    start = 0
    for i, b in enumerate(data):
        if 32 <= b < 127:
            if not cur:
                start = i
            cur.append(b)
        else:
            if len(cur) >= min_len:
                out.append({"offset": start, "text": cur.decode("ascii", "replace")})
                if len(out) >= max_results:
                    return out
            cur = bytearray()
    if len(cur) >= min_len:
        out.append({"offset": start, "text": cur.decode("ascii", "replace")})
    return out


def find_interesting(data: bytes) -> dict:
    """Scan for flag-like tokens, URLs and long base64 blobs."""
    flags = [m.group().decode("ascii", "replace") for m in _FLAG_RE.finditer(data)][:50]
    urls = [m.group().decode("ascii", "replace") for m in _URL_RE.finditer(data)][:50]
    b64s = []
    for m in _B64_RE.finditer(data):
        token = m.group()
        if len(token) % 4 == 0:
            try:
                dec = base64.b64decode(token, validate=True)
                if printable_ratio(dec) > 0.85 and len(dec) >= 4:
                    b64s.append(
                        {"encoded": token.decode("ascii"), "decoded": dec.decode("utf-8", "replace")}
                    )
            except Exception:
                pass
        if len(b64s) >= 20:
            break
    return {"flags": flags, "urls": urls, "base64": b64s}


def decode_text_variants(data: bytes, limit: int = 2000) -> dict:
    """Try common text decodings and report which are plausible."""
    sample = data[:limit]
    variants = {}
    for name, codec in (("ascii", "ascii"), ("utf-8", "utf-8"), ("utf-16-le", "utf-16-le"),
                        ("utf-16-be", "utf-16-be"), ("latin-1", "latin-1")):
        try:
            text = sample.decode(codec)
            ratio = printable_ratio(text.encode("latin-1", "replace"))
            variants[name] = {"text": text, "printable_ratio": round(ratio, 3)}
        except Exception:
            variants[name] = None
    return variants
