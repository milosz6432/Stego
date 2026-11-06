"""Format parsers and bitplane/channel analysis."""
import io
import struct
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.steganography.image import bitplanes, bmp, channels, gif, jpeg, png, tiff_webp


def test_png_chunks_and_trailing(png_appended_zip):
    a = png.analyse(png_appended_zip)
    assert a["signature_ok"]
    types = [c["type"] for c in a["chunks"]]
    assert "IHDR" in types and "IEND" in types
    assert a["trailing_data"] is not None
    assert a["trailing_data"]["size"] > 0
    assert any(an["type"] == "trailing_data" for an in a["anomalies"])


def test_png_trailing_bytes_are_zip(png_appended_zip):
    tb = png.trailing_bytes(png_appended_zip)
    assert tb[:4] == b"PK\x03\x04"


def test_png_text_chunk(tmp_path):
    from PIL import PngImagePlugin
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Comment", "FLAG{in_metadata}")
    p = tmp_path / "meta.png"
    Image.new("RGB", (8, 8)).save(p, pnginfo=meta)
    a = png.analyse(p)
    assert any(t.get("text") == "FLAG{in_metadata}" for t in a["text_chunks"])


def test_jpeg_markers_and_trailing(tmp_path):
    p = tmp_path / "x.jpg"
    Image.new("RGB", (16, 16), (120, 30, 200)).save(p, "JPEG")
    data = Path(p).read_bytes() + b"HIDDEN_TRAILER_FLAG{jpg}"
    Path(p).write_bytes(data)
    a = jpeg.analyse(p)
    assert a["signature_ok"]
    assert a["trailing_data"] is not None
    assert b"HIDDEN_TRAILER" in jpeg.trailing_bytes(p)


def test_bmp_header(tmp_path):
    p = tmp_path / "x.bmp"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(p, "BMP")
    a = bmp.analyse(p)
    assert a["signature_ok"]
    assert a["bits_per_pixel"] in (24, 32)
    assert a["width"] == 10


def test_gif_frames(tmp_path):
    p = tmp_path / "x.gif"
    # distinct frame content so Pillow keeps them separate
    frames = []
    for i in range(3):
        arr = np.full((16, 16, 3), i * 80, dtype=np.uint8)
        arr[i * 4 : i * 4 + 4, :, 0] = 255
        frames.append(Image.fromarray(arr, "RGB").convert("P"))
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=100, disposal=2)
    a = gif.analyse(p)
    assert a["frame_count"] == 3
    one = gif.extract_frame(p, 1)
    assert one[:8] == b"\x89PNG\r\n\x1a\n"


def test_tiff_ifd(tmp_path):
    p = tmp_path / "x.tiff"
    Image.new("RGB", (12, 12)).save(p, "TIFF")
    a = tiff_webp.analyse_tiff(p)
    assert a["signature_ok"]
    assert a["ifd_count"] >= 1


def test_webp_chunks(tmp_path):
    p = tmp_path / "x.webp"
    try:
        Image.new("RGB", (16, 16)).save(p, "WEBP")
    except (KeyError, OSError):
        import pytest
        pytest.skip("WebP support not built into Pillow")
    a = tiff_webp.analyse_webp(p)
    assert a["signature_ok"]
    assert len(a["chunks"]) >= 1


def test_bitplane_overview_flags_structure(bitplane_png):
    ov = bitplanes.overview(bitplane_png)
    # The planted B plane-0 checkerboard should score as structured.
    b0 = [p for p in ov["planes"] if p["channel"] == "B" and p["bit"] == 0][0]
    assert b0["structure_score"] > 0.3


def test_bitplane_render_returns_png(png_appended_zip):
    data, meta = bitplanes.render_plane(png_appended_zip, "R", 0)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert 0.0 <= meta["set_fraction"] <= 1.0


def test_channel_statistics_chi_square(png_appended_zip):
    st = channels.statistics(png_appended_zip)
    assert "R" in st["stats"]
    assert st["stats"]["R"]["lsb_chi_square"] >= 0


def test_channel_isolate_png(png_appended_zip):
    data = channels.isolate_channel(png_appended_zip, "G", grayscale=True)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
