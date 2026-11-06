"""Signature scanning, carving, archive handling, scoring, Smart Scan."""
import io
import zipfile
from pathlib import Path

import pytest

from app.analysis import scoring
from app.analysis.scoring import Finding
from app.core.job_manager import JobManager
from app.core.storage import storage
from app.extraction import payload, signatures


def test_signature_scan_finds_zip(png_appended_zip):
    data = Path(png_appended_zip).read_bytes()
    sigs = signatures.scan(data)
    assert any(s["name"] == "ZIP" for s in sigs)
    assert any(s["name"] == "PNG" and s["offset"] == 0 for s in sigs)


def test_carve_complete_zip(png_appended_zip):
    data = Path(png_appended_zip).read_bytes()
    carved = signatures.carve(data)
    zips = [c for c in carved if c["name"] == "ZIP"]
    assert zips
    # the carved bytes must be a valid zip
    zf = zipfile.ZipFile(io.BytesIO(zips[0]["data"]))
    assert "secret.txt" in zf.namelist()


def test_list_and_extract_archive(png_appended_zip):
    data = Path(png_appended_zip).read_bytes()
    carved = [c for c in signatures.carve(data) if c["name"] == "ZIP"][0]
    info = payload.list_archive(carved["data"])
    assert info["is_zip"]
    content = payload.extract_archive_entry(carved["data"], "secret.txt")
    assert b"FLAG{zip_in_png}" in content


def test_trailing_data_detection(png_appended_zip):
    tr = payload.trailing_data(png_appended_zip, "png")
    assert tr is not None
    assert tr["size"] > 0


def test_scoring_rewards_flag():
    f = scoring.score_payload(Finding("t", "m"), b"here is FLAG{scored_high} in text")
    assert f.score >= 50
    assert any("flag-like" in r.lower() for r in f.reasons)


def test_scoring_penalises_empty():
    f = scoring.score_payload(Finding("t", "m"), b"")
    assert f.score < 0


def test_smart_scan_image_recovers_zip(png_appended_zip):
    sf = storage.copy_path_in(png_appended_zip, "appended.png", origin="upload")
    jm = JobManager()
    from app.analysis.smart_scan import run_smart_scan

    job = jm.run_sync("scan", lambda p: run_smart_scan(sf.id, "standard", p))
    assert job.status == "done"
    res = job.result
    assert res["finding_count"] >= 1
    # top finding should carry the flag and a stored payload
    flags = []
    for f in res["findings"]:
        flags += f["details"].get("flags", [])
    assert any("FLAG{zip_in_png}" in x for x in flags)
    assert res["stored_payloads"]


def test_smart_scan_audio_pcm(wav_pcm):
    sf = storage.copy_path_in(wav_pcm, "pcm.wav", origin="upload")
    jm = JobManager()
    from app.analysis.smart_scan import run_smart_scan

    job = jm.run_sync("scan", lambda p: run_smart_scan(sf.id, "standard", p))
    assert job.status == "done"
    titles = " ".join(f["title"] for f in job.result["findings"])
    # PCM-LSB should recover the flag payload
    assert job.result["finding_count"] >= 1
