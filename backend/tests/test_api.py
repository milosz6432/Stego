"""End-to-end API tests via FastAPI TestClient."""
import io
import time
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from tests.conftest import embed_lsb_png, make_png_with_appended_zip

client = TestClient(app)


def _upload_png_with_zip(tmp_path):
    p = tmp_path / "api.png"
    make_png_with_appended_zip(p, "secret.txt", b"", b"FLAG{api_chain}")
    with open(p, "rb") as f:
        r = client.post("/api/files/upload", files={"file": ("api.png", f, "image/png")})
    assert r.status_code == 200
    return r.json()


def test_health():
    r = client.get("/api/system/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_tools_endpoint():
    r = client.get("/api/system/tools")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["tools"]]
    assert "zsteg" in names and "ffmpeg" in names


def test_upload_and_detect(tmp_path):
    info = _upload_png_with_zip(tmp_path)
    assert info["media_type"] == "image"
    assert info["format"] == "png"
    assert "image_lsb" in info["detection"]["applicable_modules"]


def test_hex_and_strings(tmp_path):
    info = _upload_png_with_zip(tmp_path)
    r = client.get(f"/api/files/{info['id']}/hex?length=64")
    assert r.status_code == 200
    assert len(r.json()["rows"]) > 0


def test_image_lsb_endpoint(tmp_path):
    p = tmp_path / "l.png"
    embed_lsb_png(p, b"FLAG{api_lsb}\x00")
    with open(p, "rb") as f:
        info = client.post("/api/files/upload", files={"file": ("l.png", f, "image/png")}).json()
    r = client.post("/api/image/lsb", json={
        "file_id": info["id"], "channels": ["R"], "bit_planes": [0],
        "channel_mode": "sequential", "bit_order": "msb", "traversal": "row",
    })
    assert r.status_code == 200
    assert "FLAG{api_lsb}" in r.json()["interesting"]["flags"]


def test_trailing_and_carve_auto(tmp_path):
    info = _upload_png_with_zip(tmp_path)
    r = client.get(f"/api/extraction/trailing/{info['id']}")
    assert r.json()["has_trailing"] is True
    r2 = client.post(f"/api/extraction/carve-auto/{info['id']}")
    carved = r2.json()["carved"]
    assert any(c["format"] == "ZIP" for c in carved)
    # extract the zip entry
    zip_fid = [c for c in carved if c["format"] == "ZIP"][0]["file_id"]
    r3 = client.get(f"/api/extraction/archive/{zip_fid}")
    assert r3.json()["is_zip"]
    r4 = client.post("/api/extraction/archive/extract",
                     json={"file_id": zip_fid, "entry": "secret.txt"})
    out_fid = r4.json()["file_id"]
    r5 = client.get(f"/api/files/{out_fid}/strings")
    joined = " ".join(s["text"] for s in r5.json()["strings"])
    assert "FLAG{api_chain}" in joined


def test_smart_scan_job(tmp_path):
    info = _upload_png_with_zip(tmp_path)
    r = client.post("/api/smart-scan", json={"file_id": info["id"], "depth": "quick"})
    job_id = r.json()["job_id"]
    for _ in range(60):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.2)
    assert j["status"] == "done"
    res = client.get(f"/api/jobs/{job_id}/result").json()
    assert res["finding_count"] >= 1


def test_missing_file_404():
    assert client.get("/api/files/doesnotexist").status_code == 404
    r = client.post("/api/image/lsb", json={"file_id": "nope", "channels": ["R"]})
    assert r.status_code == 404
