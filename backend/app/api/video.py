"""Video analysis API — info, frame extraction (background jobs), frame diff,
contact sheet, and audio extraction that feeds the Audio workspace."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import config
from ..core.job_manager import ProgressHandle, jobs
from ..core.storage import storage
from ..core.tools import ToolNotAvailable
from ..core.util import b64
from ..steganography.video import audio_extraction, frame_analysis, frames, info as vinfo

router = APIRouter(prefix="/api/video", tags=["video"])


def _require(file_id: str):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    return sf


def _png_url(data: bytes) -> str:
    return "data:image/png;base64," + b64(data)


def _frameset_dir(file_id: str, frameset: str) -> Path:
    # frameset is a hex token; constrain to avoid traversal
    token = "".join(c for c in frameset if c.isalnum())
    return storage.cache_dir(file_id) / f"frames_{token}"


@router.get("/info/{file_id}")
def info(file_id: str):
    sf = _require(file_id)
    try:
        return vinfo.probe(sf.stored_path)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))


class FrameExtractRequest(BaseModel):
    file_id: str
    mode: Literal["every_n", "interval", "scene"] = "every_n"
    n: int = 30
    interval: float = 1.0
    threshold: float = 0.3
    max_frames: int = 300


@router.post("/frames/extract")
def frames_extract(req: FrameExtractRequest):
    sf = _require(req.file_id)
    frameset = uuid.uuid4().hex[:12]
    out_dir = _frameset_dir(sf.id, frameset)

    def work(p: ProgressHandle):
        p.update(0.1, f"Extracting frames ({req.mode})")
        if req.mode == "every_n":
            lst = frames.extract_every_n(sf.stored_path, out_dir, n=req.n,
                                         max_frames=req.max_frames, progress=p)
        elif req.mode == "interval":
            lst = frames.extract_interval(sf.stored_path, out_dir, interval=req.interval,
                                          max_frames=req.max_frames)
        else:
            lst = frames.scene_detect(sf.stored_path, out_dir, threshold=req.threshold,
                                      max_frames=req.max_frames)
        p.update(1.0, f"Extracted {len(lst)} frames")
        return {"frameset": frameset, "count": len(lst),
                "frames": [{"index": f["index"], "name": f["name"]} for f in lst]}

    job = jobs.submit("video_frames", work, meta={"file_id": sf.id, "mode": req.mode})
    return {"job_id": job.id}


@router.get("/frames/{file_id}/{frameset}")
def list_frameset(file_id: str, frameset: str):
    _require(file_id)
    d = _frameset_dir(file_id, frameset)
    if not d.exists():
        raise HTTPException(404, "Frameset not found")
    files = sorted(list(d.glob("frame_*.png")) + list(d.glob("scene_*.png")))
    return {"frameset": frameset, "count": len(files),
            "frames": [{"index": i, "name": p.name} for i, p in enumerate(files)]}


@router.get("/frames/{file_id}/{frameset}/image/{name}")
def frame_image(file_id: str, frameset: str, name: str):
    _require(file_id)
    d = _frameset_dir(file_id, frameset)
    p = d / Path(name).name
    if not p.exists():
        raise HTTPException(404, "Frame not found")
    return {"image": _png_url(frames.frame_png(p))}


class SendFrameRequest(BaseModel):
    file_id: str
    frameset: str
    name: str


@router.post("/frames/send-to-image")
def send_frame_to_image(req: SendFrameRequest):
    """Copy a frame into storage so it can be analysed by the image module."""
    sf = _require(req.file_id)
    d = _frameset_dir(sf.id, req.frameset)
    p = d / Path(req.name).name
    if not p.exists():
        raise HTTPException(404, "Frame not found")
    out = storage.copy_path_in(p, f"{sf.name}_{req.name}", origin="frame", parent_id=sf.id,
                               meta={"source_video": sf.id, "frameset": req.frameset})
    return {"file_id": out.id, "name": out.name, "media_type": out.media_type,
            "format": out.format}


@router.get("/frames/{file_id}/{frameset}/diff")
def frameset_diff(file_id: str, frameset: str):
    _require(file_id)
    d = _frameset_dir(file_id, frameset)
    files = sorted(list(d.glob("frame_*.png")) + list(d.glob("scene_*.png")))
    if len(files) < 2:
        raise HTTPException(400, "Need at least 2 frames for difference analysis")
    return frame_analysis.difference_series(files)


@router.get("/frames/{file_id}/{frameset}/diff-image")
def frameset_diff_image(file_id: str, frameset: str, a: str, b: str, amplify: int = 1):
    _require(file_id)
    d = _frameset_dir(file_id, frameset)
    pa, pb = d / Path(a).name, d / Path(b).name
    if not pa.exists() or not pb.exists():
        raise HTTPException(404, "Frame not found")
    try:
        img = frame_analysis.difference_image(pa, pb, amplify)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"image": _png_url(img)}


@router.get("/contact-sheet/{file_id}")
def contact_sheet(file_id: str, cols: int = 5, rows: int = 5):
    sf = _require(file_id)
    out_dir = storage.cache_dir(sf.id)
    try:
        img = frames.contact_sheet(sf.stored_path, out_dir, cols=cols, rows=rows)
    except (ValueError, ToolNotAvailable) as e:
        raise HTTPException(400, str(e))
    return {"image": _png_url(img)}


@router.post("/audio/extract")
def extract_audio(file_id: str, stream: int = 0):
    sf = _require(file_id)
    out_dir = storage.cache_dir(sf.id)
    out_path = out_dir / f"audio_stream{stream}.wav"
    try:
        res = audio_extraction.extract_audio(sf.stored_path, out_path, stream=stream)
    except (ValueError, ToolNotAvailable) as e:
        raise HTTPException(400, str(e))
    stored = storage.copy_path_in(out_path, f"{sf.name}_audio{stream}.wav",
                                  origin="audio-extract", parent_id=sf.id,
                                  meta={"source_video": sf.id, "stream": stream})
    return {"file_id": stored.id, "name": stored.name, "size": stored.size,
            "media_type": stored.media_type, "format": stored.format}
