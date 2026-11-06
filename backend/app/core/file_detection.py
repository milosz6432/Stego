"""Format detection by content (magic bytes), independent of file extension.

CTF files are routinely mislabelled, so we never trust the extension for
analysis decisions. This module returns the *actual* format and a coarse
media type, plus a set of analysis modules that apply.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DetectedFormat:
    media_type: str          # image | audio | video | archive | document | data
    format: str              # png, jpeg, wav, mp4, zip, ...
    mime: str
    extension: str
    description: str
    confidence: float        # 0..1
    applicable_modules: list[str] = field(default_factory=list)


# (offset, signature bytes, media_type, format, mime, ext, description)
_SIGNATURES: list[tuple] = [
    (0, b"\x89PNG\r\n\x1a\n", "image", "png", "image/png", "png", "PNG image"),
    (0, b"\xff\xd8\xff", "image", "jpeg", "image/jpeg", "jpg", "JPEG image"),
    (0, b"GIF87a", "image", "gif", "image/gif", "gif", "GIF image (87a)"),
    (0, b"GIF89a", "image", "gif", "image/gif", "gif", "GIF image (89a)"),
    (0, b"BM", "image", "bmp", "image/bmp", "bmp", "BMP image"),
    (0, b"II*\x00", "image", "tiff", "image/tiff", "tiff", "TIFF image (little-endian)"),
    (0, b"MM\x00*", "image", "tiff", "image/tiff", "tiff", "TIFF image (big-endian)"),
    (0, b"RIFF", "data", "riff", "application/octet-stream", "bin", "RIFF container"),
    (0, b"OggS", "audio", "ogg", "audio/ogg", "ogg", "Ogg container"),
    (0, b"fLaC", "audio", "flac", "audio/flac", "flac", "FLAC audio"),
    (0, b"FORM", "audio", "aiff", "audio/aiff", "aiff", "AIFF/IFF container"),
    (0, b"ID3", "audio", "mp3", "audio/mpeg", "mp3", "MP3 audio (ID3)"),
    (0, b"\x1aE\xdf\xa3", "video", "matroska", "video/x-matroska", "mkv", "Matroska/WebM"),
    (0, b"\x00\x00\x00", "video", "mp4", "video/mp4", "mp4", "ISO Base Media (MP4/MOV)"),
    (0, b"PK\x03\x04", "archive", "zip", "application/zip", "zip", "ZIP archive"),
    (0, b"PK\x05\x06", "archive", "zip", "application/zip", "zip", "ZIP archive (empty)"),
    (0, b"Rar!\x1a\x07", "archive", "rar", "application/x-rar", "rar", "RAR archive"),
    (0, b"\x1f\x8b", "archive", "gzip", "application/gzip", "gz", "gzip stream"),
    (0, b"7z\xbc\xaf\x27\x1c", "archive", "7z", "application/x-7z-compressed", "7z", "7-Zip archive"),
    (0, b"%PDF", "document", "pdf", "application/pdf", "pdf", "PDF document"),
    (0, b"\x42\x5a\x68", "archive", "bzip2", "application/x-bzip2", "bz2", "bzip2 stream"),
]

_MODULES_BY_MEDIA = {
    "image": ["image_lsb", "image_bitplanes", "image_channels", "image_format",
              "image_tools", "extraction"],
    "audio": ["audio_waveform", "audio_spectrogram", "audio_fft", "audio_pcm_lsb",
              "audio_advanced", "audio_decoders", "extraction"],
    "video": ["video_info", "video_frames", "video_audio", "extraction"],
    "archive": ["extraction"],
    "document": ["extraction"],
    "data": ["extraction"],
}


def _mp4_brand(head: bytes) -> Optional[tuple]:
    """MP4/MOV family uses an ftyp box; size prefix then 'ftyp'."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand[:3] == b"qt ":
            return ("video", "mov", "video/quicktime", "mov", "QuickTime MOV")
        return ("video", "mp4", "video/mp4", "mp4", f"MP4 (brand {brand.decode('latin-1', 'replace')})")
    return None


def _riff_subtype(head: bytes) -> Optional[tuple]:
    """RIFF wraps WAV, AVI, WebP — disambiguate by the form type at offset 8."""
    if len(head) < 12 or head[:4] != b"RIFF":
        return None
    form = head[8:12]
    if form == b"WAVE":
        return ("audio", "wav", "audio/wav", "wav", "WAV audio (RIFF/WAVE)")
    if form == b"AVI ":
        return ("video", "avi", "video/x-msvideo", "avi", "AVI video (RIFF)")
    if form == b"WEBP":
        return ("image", "webp", "image/webp", "webp", "WebP image (RIFF)")
    return None


def detect_bytes(head: bytes, declared_name: str = "") -> DetectedFormat:
    """Detect format from the leading bytes of a file."""
    # Context-sensitive containers first.
    riff = _riff_subtype(head)
    if riff:
        mt, fmt, mime, ext, desc = riff
        return _build(mt, fmt, mime, ext, desc, 0.99)

    mp4 = _mp4_brand(head)
    if mp4:
        mt, fmt, mime, ext, desc = mp4
        return _build(mt, fmt, mime, ext, desc, 0.97)

    for offset, sig, mt, fmt, mime, ext, desc in _SIGNATURES:
        if fmt == "mp4" and sig == b"\x00\x00\x00":
            # handled above via ftyp; only a weak fallback
            continue
        if head[offset:offset + len(sig)] == sig:
            return _build(mt, fmt, mime, ext, desc, 0.98)

    # MP3 without ID3: frame sync 0xFFEx / 0xFFFx
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return _build("audio", "mp3", "audio/mpeg", "mp3", "MP3 audio (frame sync)", 0.7)

    # Fall back on extension as a hint only.
    ext = Path(declared_name).suffix.lower().lstrip(".")
    guess = _EXT_FALLBACK.get(ext)
    if guess:
        mt, fmt, mime, desc = guess
        return _build(mt, fmt, mime, ext, desc + " (by extension — magic bytes not recognised)", 0.3)

    return _build("data", "unknown", "application/octet-stream", ext or "bin",
                  "Unknown / raw data", 0.1)


_EXT_FALLBACK = {
    "png": ("image", "png", "image/png", "PNG image"),
    "jpg": ("image", "jpeg", "image/jpeg", "JPEG image"),
    "jpeg": ("image", "jpeg", "image/jpeg", "JPEG image"),
    "bmp": ("image", "bmp", "image/bmp", "BMP image"),
    "gif": ("image", "gif", "image/gif", "GIF image"),
    "tiff": ("image", "tiff", "image/tiff", "TIFF image"),
    "tif": ("image", "tiff", "image/tiff", "TIFF image"),
    "webp": ("image", "webp", "image/webp", "WebP image"),
    "wav": ("audio", "wav", "audio/wav", "WAV audio"),
    "flac": ("audio", "flac", "audio/flac", "FLAC audio"),
    "mp3": ("audio", "mp3", "audio/mpeg", "MP3 audio"),
    "ogg": ("audio", "ogg", "audio/ogg", "Ogg audio"),
    "aiff": ("audio", "aiff", "audio/aiff", "AIFF audio"),
    "aif": ("audio", "aiff", "audio/aiff", "AIFF audio"),
    "mp4": ("video", "mp4", "video/mp4", "MP4 video"),
    "mkv": ("video", "matroska", "video/x-matroska", "Matroska video"),
    "mov": ("video", "mov", "video/quicktime", "QuickTime video"),
    "avi": ("video", "avi", "video/x-msvideo", "AVI video"),
}


def _build(media_type: str, fmt: str, mime: str, ext: str, desc: str, conf: float) -> DetectedFormat:
    return DetectedFormat(
        media_type=media_type,
        format=fmt,
        mime=mime,
        extension=ext,
        description=desc,
        confidence=conf,
        applicable_modules=list(_MODULES_BY_MEDIA.get(media_type, ["extraction"])),
    )


def detect_file(path: str | Path) -> DetectedFormat:
    p = Path(path)
    with open(p, "rb") as f:
        head = f.read(64)
    return detect_bytes(head, declared_name=p.name)
