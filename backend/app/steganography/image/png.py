"""PNG structural analysis.

Parses the chunk stream, flags anomalies (bad CRC, unknown/duplicate chunks,
data after IEND), decodes IHDR, and surfaces text chunks (tEXt/zTXt/iTXt)
which frequently carry CTF hints.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from ...core.util import b64, hex_dump, printable_ratio

PNG_SIG = b"\x89PNG\r\n\x1a\n"

_KNOWN = {
    "IHDR", "PLTE", "IDAT", "IEND", "tRNS", "cHRM", "gAMA", "iCCP", "sBIT",
    "sRGB", "tEXt", "zTXt", "iTXt", "bKGD", "hIST", "pHYs", "sPLT", "tIME",
    "acTL", "fcTL", "fdAT", "eXIf",
}

_COLOR_TYPES = {
    0: "Grayscale", 2: "Truecolour", 3: "Indexed", 4: "Grayscale+Alpha", 6: "Truecolour+Alpha",
}


def analyse(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    if data[:8] != PNG_SIG:
        raise ValueError("Not a PNG file (bad signature)")

    chunks = []
    anomalies = []
    text_chunks = []
    pos = 8
    ihdr = None
    idat_total = 0
    seen_iend_at = None

    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8].decode("latin-1", "replace")
        body_start = pos + 8
        body_end = body_start + length
        if body_end + 4 > len(data):
            anomalies.append({"type": "truncated_chunk", "chunk": ctype, "offset": pos,
                              "detail": "Chunk length runs past end of file"})
            break
        body = data[body_start:body_end]
        (crc_stored,) = struct.unpack(">I", data[body_end:body_end + 4])
        crc_calc = zlib.crc32(data[pos + 4:body_end]) & 0xFFFFFFFF
        crc_ok = crc_stored == crc_calc

        entry = {
            "type": ctype,
            "offset": pos,
            "length": length,
            "crc_ok": crc_ok,
            "known": ctype in _KNOWN,
            "critical": ctype[0].isupper(),
        }
        if not crc_ok:
            anomalies.append({"type": "bad_crc", "chunk": ctype, "offset": pos,
                              "detail": f"stored={crc_stored:08x} calc={crc_calc:08x}"})
        if ctype not in _KNOWN:
            anomalies.append({"type": "unknown_chunk", "chunk": ctype, "offset": pos,
                              "detail": "Non-standard chunk type — possible carrier"})

        if ctype == "IHDR" and length >= 13:
            w, h, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", body[:13])
            ihdr = {
                "width": w, "height": h, "bit_depth": depth,
                "color_type": color, "color_type_name": _COLOR_TYPES.get(color, "?"),
                "compression": comp, "filter": filt, "interlace": interlace,
            }
            entry["parsed"] = ihdr
        elif ctype == "IDAT":
            idat_total += length
        elif ctype == "IEND":
            seen_iend_at = body_end + 4
        elif ctype in ("tEXt", "zTXt", "iTXt"):
            text_chunks.append(_parse_text_chunk(ctype, body))

        chunks.append(entry)
        pos = body_end + 4
        if ctype == "IEND":
            break

    trailing = None
    if seen_iend_at is not None and seen_iend_at < len(data):
        extra = data[seen_iend_at:]
        trailing = {
            "offset": seen_iend_at,
            "size": len(extra),
            "printable_ratio": round(printable_ratio(extra), 3),
            "hex": hex_dump(extra[:512], offset=seen_iend_at),
            "base64": b64(extra[:1 << 20]),
            "preview": extra[:256].decode("latin-1", "replace"),
        }
        anomalies.append({"type": "trailing_data", "offset": seen_iend_at,
                          "detail": f"{len(extra)} bytes after IEND — common stego hiding spot"})

    return {
        "signature_ok": True,
        "ihdr": ihdr,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "idat_total_bytes": idat_total,
        "text_chunks": text_chunks,
        "trailing_data": trailing,
        "anomalies": anomalies,
    }


def _parse_text_chunk(ctype: str, body: bytes) -> dict:
    try:
        if ctype == "tEXt":
            key, _, val = body.partition(b"\x00")
            return {"type": ctype, "keyword": key.decode("latin-1", "replace"),
                    "text": val.decode("latin-1", "replace")}
        if ctype == "zTXt":
            key, _, rest = body.partition(b"\x00")
            comp_method = rest[0] if rest else 0
            val = zlib.decompress(rest[1:]) if len(rest) > 1 else b""
            return {"type": ctype, "keyword": key.decode("latin-1", "replace"),
                    "text": val.decode("latin-1", "replace"), "compressed": True}
        if ctype == "iTXt":
            parts = body.split(b"\x00", 5)
            keyword = parts[0].decode("utf-8", "replace") if parts else ""
            text = parts[-1] if len(parts) == 6 else b""
            # compression flag is parts[1][0]; handle both
            if len(parts) >= 3 and parts[1:2] == [b"\x01"]:
                try:
                    text = zlib.decompress(text)
                except Exception:
                    pass
            return {"type": ctype, "keyword": keyword,
                    "text": text.decode("utf-8", "replace")}
    except Exception as e:  # noqa: BLE001
        return {"type": ctype, "error": str(e)}
    return {"type": ctype, "raw": body[:200].decode("latin-1", "replace")}


def trailing_bytes(path: str | Path) -> bytes:
    """Return the raw bytes found after IEND (for extraction), or b''."""
    data = Path(path).read_bytes()
    idx = data.find(b"IEND")
    if idx == -1:
        return b""
    end = idx + 8  # IEND + 4-byte CRC
    return data[end:] if end < len(data) else b""
