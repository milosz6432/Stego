"""External tool integrations. Each test skips cleanly if the tool is absent,
so the suite passes on a minimal install and really exercises tools when present."""
import numpy as np
import pytest
from PIL import Image

from app.core import tools
from app.steganography.image import tool_integration as ti


@pytest.fixture
def bmp_cover(tmp_path):
    p = tmp_path / "cover.bmp"
    Image.fromarray(np.random.default_rng(5).integers(0, 256, (200, 200, 3), dtype=np.uint8), "RGB").save(p)
    return p


def test_steghide_roundtrip(tmp_path, bmp_cover):
    if not tools.available("steghide"):
        pytest.skip("steghide not installed")
    secret = tmp_path / "s.txt"
    secret.write_text("STEGHIDE_ROUNDTRIP_FLAG")
    stego = tmp_path / "stego.bmp"
    res = tools.run_tool("steghide", ["embed", "-cf", str(bmp_cover), "-ef", str(secret),
                                      "-p", "pw", "-sf", str(stego), "-q"])
    assert res.ok, res.stderr
    payload, info = ti.steghide_extract_payload(stego, "pw")
    assert info["ok"]
    assert payload == b"STEGHIDE_ROUNDTRIP_FLAG"


def test_steghide_wrong_passphrase_reports_failure(tmp_path, bmp_cover):
    if not tools.available("steghide"):
        pytest.skip("steghide not installed")
    secret = tmp_path / "s.txt"
    secret.write_text("secret")
    stego = tmp_path / "stego.bmp"
    tools.run_tool("steghide", ["embed", "-cf", str(bmp_cover), "-ef", str(secret),
                                "-p", "correct", "-sf", str(stego), "-q"])
    payload, info = ti.steghide_extract_payload(stego, "wrong")
    # must NOT fabricate success
    assert info["ok"] is False


def test_zsteg_runs(tmp_path):
    if not tools.available("zsteg"):
        pytest.skip("zsteg not installed")
    p = tmp_path / "z.png"
    Image.fromarray(np.random.default_rng(6).integers(0, 256, (40, 40, 3), dtype=np.uint8), "RGB").save(p)
    out = ti.run_zsteg(p, all_methods=False)
    assert "command" in out
    assert "argv" in out["command"]


def test_exiftool(tmp_path):
    if not tools.available("exiftool"):
        pytest.skip("exiftool not installed")
    p = tmp_path / "e.png"
    Image.new("RGB", (8, 8)).save(p)
    out = ti.run_exiftool(p)
    assert out["ok"]
    assert out["metadata"] is not None


def test_ffprobe_on_wav(wav_pcm):
    from app.steganography.video import info
    if not tools.available("ffprobe"):
        pytest.skip("ffprobe not installed")
    pr = info.probe(wav_pcm)
    assert pr["ok"]
    assert pr["audio_streams"]
