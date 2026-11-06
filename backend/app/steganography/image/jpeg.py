"""JPEG structural analysis.

Walks the marker/segment stream, decodes APPn segments (EXIF/JFIF/Adobe),
captures the comment (COM) segment, and detects data appended after the EOI
marker — all common hiding spots in CTF JPEGs.
"""
from __future__ import annotations

from pathlib import Path

from ...core.util import b64, hex_dump, printable_ratio

# Markers that are standalone (no length field)
_STANDALONE = {0xD8, 0xD9} | set(range(0xD0, 0xD8))  # SOI, EOI, RSTn

_MARKER_NAMES = {
    0xD8: "SOI", 0xD9: "EOI", 0xDA: "SOS", 0xDB: "DQT", 0xC4: "DHT",
    0xDD: "DRI", 0xFE: "COM",
    0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2", 0xC3: "SOF3",
    **{0xE0 + i: f"APP{i}" for i in range(16)},
}


def analyse(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError("Not a JPEG file (missing SOI)")

    segments = []
    anomalies = []
    comments = []
    app_segments = []
    pos = 2
    eoi_at = None
    n = len(data)

    while pos < n:
        if data[pos] != 0xFF:
            # skip fill bytes / entropy-coded data; find next marker
            nxt = data.find(b"\xff", pos)
            if nxt == -1:
                break
            pos = nxt
            continue
        # consume fill 0xFF
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        name = _MARKER_NAMES.get(marker, f"0x{marker:02X}")

        if marker == 0xD9:  # EOI
            eoi_at = pos
            segments.append({"marker": name, "code": marker, "offset": pos - 2})
            break
        if marker in _STANDALONE or marker == 0x01:
            segments.append({"marker": name, "code": marker, "offset": pos - 2})
            continue

        if pos + 2 > n:
            anomalies.append({"type": "truncated", "detail": f"segment {name} length runs past EOF"})
            break
        seg_len = (data[pos] << 8) | data[pos + 1]
        body = data[pos + 2:pos + seg_len]
        seg = {"marker": name, "code": marker, "offset": pos - 2, "length": seg_len}

        if marker == 0xFE:  # COM
            text = body.decode("latin-1", "replace")
            comments.append(text)
            seg["comment"] = text
        elif 0xE0 <= marker <= 0xEF:  # APPn
            ident = body.split(b"\x00", 1)[0][:16].decode("latin-1", "replace")
            app_segments.append({"marker": name, "identifier": ident, "length": seg_len})
            seg["identifier"] = ident

        segments.append(seg)

        if marker == 0xDA:  # SOS: entropy-coded data follows until next marker/EOI
            pos = pos + seg_len
            # scan to EOI
            scan = data.find(b"\xff\xd9", pos)
            if scan != -1:
                eoi_at = scan + 2
            else:
                eoi_at = None
            segments.append({"marker": "EOI", "code": 0xD9,
                             "offset": (eoi_at - 2) if eoi_at else None})
            break
        pos += seg_len

    trailing = None
    if eoi_at is not None and eoi_at < n:
        extra = data[eoi_at:]
        trailing = {
            "offset": eoi_at,
            "size": len(extra),
            "printable_ratio": round(printable_ratio(extra), 3),
            "hex": hex_dump(extra[:512], offset=eoi_at),
            "base64": b64(extra[:1 << 20]),
            "preview": extra[:256].decode("latin-1", "replace"),
        }
        anomalies.append({"type": "trailing_data", "offset": eoi_at,
                          "detail": f"{len(extra)} bytes after EOI — common stego hiding spot"})

    return {
        "signature_ok": True,
        "segment_count": len(segments),
        "segments": segments,
        "app_segments": app_segments,
        "comments": comments,
        "eoi_offset": eoi_at,
        "trailing_data": trailing,
        "anomalies": anomalies,
    }


def trailing_bytes(path: str | Path) -> bytes:
    data = Path(path).read_bytes()
    idx = data.rfind(b"\xff\xd9")
    if idx == -1:
        return b""
    end = idx + 2
    return data[end:] if end < len(data) else b""
