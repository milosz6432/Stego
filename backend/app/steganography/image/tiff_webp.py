"""TIFF (IFD structure) and WebP (RIFF chunk) structural analysis."""
from __future__ import annotations

import struct
from pathlib import Path

from ...core.util import b64, hex_dump, printable_ratio

# ---- TIFF -------------------------------------------------------------------
_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
_TIFF_TAGS = {
    256: "ImageWidth", 257: "ImageLength", 258: "BitsPerSample", 259: "Compression",
    262: "PhotometricInterpretation", 273: "StripOffsets", 277: "SamplesPerPixel",
    278: "RowsPerStrip", 279: "StripByteCounts", 282: "XResolution", 283: "YResolution",
    305: "Software", 306: "DateTime", 315: "Artist", 270: "ImageDescription",
}


def analyse_tiff(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    if data[:2] == b"II":
        endian = "<"
    elif data[:2] == b"MM":
        endian = ">"
    else:
        raise ValueError("Not a TIFF file")

    (magic,) = struct.unpack(endian + "H", data[2:4])
    (ifd_off,) = struct.unpack(endian + "I", data[4:8])
    ifds = []
    anomalies = []
    visited = set()

    while ifd_off and ifd_off not in visited and ifd_off + 2 <= len(data):
        visited.add(ifd_off)
        (count,) = struct.unpack(endian + "H", data[ifd_off:ifd_off + 2])
        entries = []
        p = ifd_off + 2
        for _ in range(count):
            if p + 12 > len(data):
                anomalies.append({"type": "truncated_ifd", "offset": p})
                break
            tag, ftype, n = struct.unpack(endian + "HHI", data[p:p + 8])
            raw_val = data[p + 8:p + 12]
            entries.append({
                "tag": tag,
                "name": _TIFF_TAGS.get(tag, f"Unknown({tag})"),
                "type": ftype,
                "count": n,
                "value_bytes": raw_val.hex(),
            })
            p += 12
        (next_off,) = struct.unpack(endian + "I", data[p:p + 4]) if p + 4 <= len(data) else (0,)
        ifds.append({"offset": ifd_off, "entry_count": count, "entries": entries,
                     "next_ifd": next_off})
        ifd_off = next_off

    return {
        "signature_ok": True,
        "endianness": "little" if endian == "<" else "big",
        "magic": magic,
        "ifd_count": len(ifds),
        "ifds": ifds,
        "anomalies": anomalies,
    }


# ---- WebP (RIFF) ------------------------------------------------------------
def analyse_webp(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("Not a WebP file")
    (riff_size,) = struct.unpack("<I", data[4:8])
    declared_total = riff_size + 8

    chunks = []
    anomalies = []
    pos = 12
    n = len(data)
    while pos + 8 <= n:
        fourcc = data[pos:pos + 4].decode("latin-1", "replace")
        (size,) = struct.unpack("<I", data[pos + 4:pos + 8])
        body_start = pos + 8
        chunks.append({"fourcc": fourcc, "offset": pos, "size": size})
        advance = 8 + size + (size & 1)  # chunks are padded to even size
        pos += advance
    if declared_total < n:
        extra = data[declared_total:]
        anomalies.append({"type": "trailing_data", "offset": declared_total,
                          "size": len(extra),
                          "detail": f"{len(extra)} bytes after RIFF payload"})
    return {
        "signature_ok": True,
        "riff_declared_size": declared_total,
        "file_size": n,
        "chunks": chunks,
        "anomalies": anomalies,
    }
