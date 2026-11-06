"""Payload extraction: trailing data, carved embedded files, archive contents.

Ties together the per-format trailing-data detectors (PNG after IEND, JPEG
after EOI, BMP after pixel data) and the generic signature carver, and can
list/extract the contents of recovered archives (ZIP) for the classic
PNG -> ZIP -> text CTF chain.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

from ..core.util import b64, hex_dump, printable_ratio, find_interesting
from ..steganography.image import bmp, jpeg, png
from . import signatures


def trailing_data(path: str | Path, fmt: str) -> Optional[dict]:
    """Return trailing bytes after the format's logical end, if any."""
    raw = b""
    if fmt == "png":
        raw = png.trailing_bytes(path)
    elif fmt == "jpeg":
        raw = jpeg.trailing_bytes(path)
    elif fmt == "bmp":
        analysis = bmp.analyse(path)
        if analysis.get("trailing_data"):
            off = analysis["trailing_data"]["offset"]
            raw = Path(path).read_bytes()[off:]
    if not raw:
        return None
    return {
        "size": len(raw),
        "printable_ratio": round(printable_ratio(raw), 3),
        "signatures": signatures.scan(raw, max_results=20),
        "data": raw,
    }


def analyse_blob(data: bytes) -> dict:
    """Full payload analysis of an arbitrary byte blob."""
    sigs = signatures.scan(data, max_results=100)
    carved = signatures.carve(data, max_files=50)
    interesting = find_interesting(data)
    return {
        "size": len(data),
        "printable_ratio": round(printable_ratio(data), 3),
        "signatures": sigs,
        "carved": [{"name": c["name"], "ext": c["ext"], "offset": c["offset"],
                    "size": c["size"], "description": c["description"]} for c in carved],
        "carved_data": carved,     # includes bytes; not serialised directly to client
        "interesting": interesting,
        "hex": hex_dump(data[:512]),
    }


def list_archive(data: bytes) -> dict:
    """If *data* is a ZIP, list its entries (does not extract to disk)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"is_zip": False}
    entries = []
    for zi in zf.infolist():
        entries.append({
            "name": zi.filename,
            "size": zi.file_size,
            "compressed": zi.compress_size,
            "is_dir": zi.is_dir(),
            "encrypted": bool(zi.flag_bits & 0x1),
        })
    return {"is_zip": True, "entries": entries, "count": len(entries)}


def extract_archive_entry(data: bytes, name: str, password: Optional[str] = None) -> bytes:
    zf = zipfile.ZipFile(io.BytesIO(data))
    pwd = password.encode() if password else None
    return zf.read(name, pwd=pwd)
