"""BMP structural analysis: headers, colour depth, row padding, pixel region
size vs file size (detects appended data and oversized gaps)."""
from __future__ import annotations

import struct
from pathlib import Path

from ...core.util import b64, hex_dump, printable_ratio


def analyse(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    if data[:2] != b"BM":
        raise ValueError("Not a BMP file")
    if len(data) < 54:
        raise ValueError("BMP too small for a header")

    file_size, _, _, pixel_offset = struct.unpack("<IHHI", data[2:14])
    dib_size = struct.unpack("<I", data[14:18])[0]
    width, height = struct.unpack("<ii", data[18:26])
    planes, bpp = struct.unpack("<HH", data[26:30])
    compression, image_size = struct.unpack("<II", data[30:38])

    row_bytes = ((bpp * abs(width) + 31) // 32) * 4   # rows are padded to 4 bytes
    expected_pixels = row_bytes * abs(height)
    padding_per_row = row_bytes - ((bpp * abs(width) + 7) // 8)

    anomalies = []
    if file_size != len(data):
        anomalies.append({"type": "size_mismatch",
                          "detail": f"Header file_size={file_size} but actual={len(data)}"})
    pixel_end = pixel_offset + expected_pixels
    trailing = None
    if pixel_end < len(data):
        extra = data[pixel_end:]
        trailing = {
            "offset": pixel_end, "size": len(extra),
            "printable_ratio": round(printable_ratio(extra), 3),
            "hex": hex_dump(extra[:512], offset=pixel_end),
            "base64": b64(extra[:1 << 20]),
        }
        anomalies.append({"type": "trailing_data", "offset": pixel_end,
                          "detail": f"{len(extra)} bytes after pixel data"})
    if padding_per_row > 0:
        anomalies.append({"type": "row_padding", "detail":
                          f"{padding_per_row} padding byte(s) per row — can carry hidden data"})

    return {
        "signature_ok": True,
        "file_size_header": file_size,
        "file_size_actual": len(data),
        "pixel_offset": pixel_offset,
        "dib_header_size": dib_size,
        "width": width, "height": height,
        "bits_per_pixel": bpp,
        "planes": planes,
        "compression": compression,
        "declared_image_size": image_size,
        "row_stride_bytes": row_bytes,
        "padding_bytes_per_row": padding_per_row,
        "trailing_data": trailing,
        "anomalies": anomalies,
    }
