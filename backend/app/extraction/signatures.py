"""File signature detection and carving.

A compact magic-number table with headers and (where defined) footers lets us
both *detect* embedded file types and *carve* complete embedded files out of a
larger blob — the bread-and-butter of CTF payload recovery.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Signature:
    name: str
    ext: str
    header: bytes
    footer: Optional[bytes] = None
    description: str = ""
    carver: Optional[Callable] = None   # custom length function(data, start) -> end


SIGNATURES: list[Signature] = [
    Signature("ZIP", "zip", b"PK\x03\x04", description="ZIP archive / OOXML / JAR / APK"),
    Signature("PNG", "png", b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82", "PNG image"),
    Signature("JPEG", "jpg", b"\xff\xd8\xff", b"\xff\xd9", "JPEG image"),
    Signature("GIF", "gif", b"GIF89a", b"\x00\x3b", "GIF image"),
    Signature("GIF87", "gif", b"GIF87a", b"\x00\x3b", "GIF image (87a)"),
    Signature("PDF", "pdf", b"%PDF", b"%%EOF", "PDF document"),
    Signature("RAR", "rar", b"Rar!\x1a\x07", description="RAR archive"),
    Signature("7Z", "7z", b"7z\xbc\xaf\x27\x1c", description="7-Zip archive"),
    Signature("GZIP", "gz", b"\x1f\x8b\x08", description="gzip stream"),
    Signature("BZIP2", "bz2", b"BZh", description="bzip2 stream"),
    Signature("XZ", "xz", b"\xfd7zXZ\x00", description="xz stream"),
    Signature("ELF", "elf", b"\x7fELF", description="ELF executable"),
    Signature("PE", "exe", b"MZ", description="DOS/PE executable"),
    Signature("WAV", "wav", b"RIFF", description="RIFF/WAV container"),
    Signature("OGG", "ogg", b"OggS", description="Ogg container"),
    Signature("FLAC", "flac", b"fLaC", description="FLAC audio"),
    Signature("MP3", "mp3", b"ID3", description="MP3 audio (ID3)"),
    Signature("BMP", "bmp", b"BM", description="BMP image"),
    Signature("TIFF_LE", "tiff", b"II*\x00", description="TIFF (little-endian)"),
    Signature("TIFF_BE", "tiff", b"MM\x00*", description="TIFF (big-endian)"),
    Signature("CLASS", "class", b"\xca\xfe\xba\xbe", description="Java class"),
    Signature("SQLITE", "sqlite", b"SQLite format 3\x00", description="SQLite database"),
    Signature("MATROSKA", "mkv", b"\x1aE\xdf\xa3", description="Matroska/WebM"),
    Signature("PCAP", "pcap", b"\xd4\xc3\xb2\xa1", description="PCAP capture"),
    Signature("PCAPNG", "pcapng", b"\x0a\x0d\x0d\x0a", description="PCAPNG capture"),
]


def scan(data: bytes, *, min_offset: int = 0, max_results: int = 500) -> list[dict]:
    """Return every signature occurrence (header matches) in *data*."""
    results = []
    for sig in SIGNATURES:
        start = min_offset
        while True:
            idx = data.find(sig.header, start)
            if idx == -1:
                break
            results.append({
                "name": sig.name, "ext": sig.ext, "offset": idx,
                "description": sig.description, "has_footer": sig.footer is not None,
            })
            start = idx + 1
            if len(results) >= max_results:
                results.sort(key=lambda r: r["offset"])
                return results
    results.sort(key=lambda r: r["offset"])
    return results


def _carve_zip_length(data: bytes, start: int) -> Optional[int]:
    """Find the End Of Central Directory record to size a ZIP precisely."""
    eocd = data.rfind(b"PK\x05\x06", start)
    if eocd == -1 or eocd + 22 > len(data):
        return None
    comment_len = struct.unpack("<H", data[eocd + 20:eocd + 22])[0]
    return eocd + 22 + comment_len - start


def carve(data: bytes, *, max_files: int = 50) -> list[dict]:
    """Carve complete embedded files using headers + footers where known.

    Returns dicts with offset, size and the carved bytes (base64-free; the
    caller stores them). Only *embedded* files (not the whole blob) are
    reported when a header appears at offset > 0, but a header at offset 0 is
    still carved so recursive analysis works on raw payloads.
    """
    out = []
    for sig in SIGNATURES:
        start = 0
        while len(out) < max_files:
            idx = data.find(sig.header, start)
            if idx == -1:
                break
            start = idx + 1
            end = None
            if sig.name == "ZIP":
                length = _carve_zip_length(data, idx)
                end = (idx + length) if length else None
            elif sig.footer:
                fidx = data.find(sig.footer, idx + len(sig.header))
                if fidx != -1:
                    end = fidx + len(sig.footer)
            if end and end > idx and (end - idx) >= 8:
                chunk = data[idx:end]
                out.append({
                    "name": sig.name, "ext": sig.ext, "offset": idx,
                    "size": len(chunk), "data": chunk,
                    "description": sig.description,
                })
    out.sort(key=lambda r: r["offset"])
    return out
