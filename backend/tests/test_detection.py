"""Format detection by magic bytes."""
from app.core.file_detection import detect_bytes, detect_file


def test_png_detection(png_lsb):
    d = detect_file(png_lsb)
    assert d.media_type == "image"
    assert d.format == "png"
    assert d.confidence > 0.9


def test_wav_detection(wav_pcm):
    d = detect_file(wav_pcm)
    assert d.media_type == "audio"
    assert d.format == "wav"


def test_riff_disambiguation():
    assert detect_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ").format == "wav"
    assert detect_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ").format == "webp"
    assert detect_bytes(b"RIFF\x00\x00\x00\x00AVI LIST").format == "avi"


def test_zip_and_pdf():
    assert detect_bytes(b"PK\x03\x04rest").format == "zip"
    assert detect_bytes(b"%PDF-1.7").format == "pdf"


def test_unknown_falls_back_to_data():
    d = detect_bytes(b"\x01\x02\x03nothing special")
    assert d.media_type == "data"
    assert d.format == "unknown"


def test_extension_is_not_trusted(tmp_path):
    # PNG bytes with a .jpg name must still detect as PNG
    p = tmp_path / "trick.jpg"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert detect_file(p).format == "png"
