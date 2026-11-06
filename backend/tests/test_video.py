"""Video: probe, frame extraction, diff, audio extraction (needs ffmpeg)."""
import subprocess

import pytest

from app.core import tools
from app.steganography.video import audio_extraction, frame_analysis, frames, info


@pytest.fixture
def sample_video(tmp_path):
    if not tools.available("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "v.mp4"
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", str(out)],
        capture_output=True,
    )
    if r.returncode != 0 or not out.exists():
        pytest.skip("ffmpeg could not build a sample video")
    return out


def test_probe(sample_video):
    pr = info.probe(sample_video)
    assert pr["ok"]
    assert pr["video_streams"][0]["width"] == 160
    assert pr["audio_streams"]


def test_extract_frames_and_diff(sample_video, tmp_path):
    d = tmp_path / "frames"
    lst = frames.extract_every_n(sample_video, d, n=3, max_frames=10)
    assert len(lst) >= 2
    diff = frame_analysis.difference_series([f["path"] for f in lst])
    assert diff["frame_count"] == len(lst)
    assert len(diff["differences"]) == len(lst) - 1


def test_contact_sheet(sample_video, tmp_path):
    png = frames.contact_sheet(sample_video, tmp_path / "sheet", cols=2, rows=2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_extract_audio(sample_video, tmp_path):
    out = tmp_path / "a.wav"
    res = audio_extraction.extract_audio(sample_video, out)
    assert res["ok"]
    assert out.exists()
    # the extracted audio must be analysable as lossless PCM
    from app.steganography.audio.loader import load_audio
    a = load_audio(out)
    assert a.is_lossless_pcm
