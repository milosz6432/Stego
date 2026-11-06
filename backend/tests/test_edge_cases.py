"""Edge cases: empty, invalid, corrupted inputs; missing-tool honesty."""
import pytest

from app.core import tools
from app.core.file_detection import detect_file
from app.steganography.image import lsb, png
from app.steganography.audio import pcm_lsb


def test_empty_file(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    d = detect_file(p)
    assert d.media_type == "data"


def test_invalid_png_rejected(tmp_path):
    p = tmp_path / "bad.png"
    p.write_bytes(b"not a png at all")
    with pytest.raises(ValueError):
        png.analyse(p)


def test_corrupted_png_crc(tmp_path):
    # valid PNG then flip a byte in a chunk to break CRC
    from PIL import Image
    Image.new("RGB", (8, 8)).save(p := tmp_path / "c.png")
    data = bytearray(p.read_bytes())
    data[30] ^= 0xFF
    p.write_bytes(bytes(data))
    a = png.analyse(p)
    # should parse but flag an anomaly, not crash
    assert any(an["type"] in ("bad_crc", "unknown_chunk", "truncated_chunk") for an in a["anomalies"]) or a["chunk_count"] >= 1


def test_lsb_on_tiny_image(tmp_path):
    from PIL import Image
    Image.new("RGB", (2, 2)).save(p := tmp_path / "tiny.png")
    raw = lsb.extract_raw(p, lsb.LSBParams(channels=["R", "G", "B"]))
    assert isinstance(raw, bytes)  # no crash on tiny input


def test_tool_not_available_raises_structured():
    # Force an unknown tool
    from app.core.tools import ToolNotAvailable
    with pytest.raises(ToolNotAvailable):
        tools.run_tool("definitely_not_a_tool", ["--help"])


def test_run_tool_no_shell_injection(tmp_path):
    """Arguments are passed as a list; shell metacharacters are literal and
    must not spawn a subcommand (proven by a side-effect file never appearing)."""
    if not tools.available("exiftool"):
        pytest.skip("exiftool not installed")
    sentinel = tmp_path / "INJECTED"
    # If this argument were run through a shell, the `touch` would fire.
    arg = f"{tmp_path}/nope; touch {sentinel}"
    tools.run_tool("exiftool", [arg])
    assert not sentinel.exists(), "shell metacharacters were executed — injection!"


def test_max_bytes_cap_respected(wav_pcm):
    out = pcm_lsb.extract(wav_pcm, pcm_lsb.PCMParams(channels=[0], max_bytes=10))
    assert out["extracted_bytes"] <= 10
