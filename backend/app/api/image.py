"""Image steganography API.

Exposes the LSB engine, bitplane viewer, channel analysis, per-format
structural parsers, and external tool integrations. Rendered images are
returned as base64 PNG data URLs; extracted payloads are stored and returned
with a file id so they flow into the Results workspace and can be re-analysed.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core import tools
from ..core.storage import storage
from ..core.tools import ToolNotAvailable
from ..core.util import b64
from ..steganography.image import (
    bitplanes,
    bmp,
    channels,
    gif,
    jpeg,
    lsb,
    png,
    tiff_webp,
    tool_integration as ti,
)

router = APIRouter(prefix="/api/image", tags=["image"])


def _png_data_url(data: bytes) -> str:
    return "data:image/png;base64," + b64(data)


def _require_image(file_id: str):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    return sf


# ---- LSB --------------------------------------------------------------------
class LSBRequest(BaseModel):
    file_id: str
    channels: list[str] = Field(default_factory=lambda: ["R", "G", "B"])
    bit_planes: list[int] = Field(default_factory=lambda: [0])
    traversal: Literal["row", "column"] = "row"
    channel_mode: Literal["interleave", "sequential"] = "interleave"
    bit_order: Literal["msb", "lsb"] = "msb"
    plane_order: Literal["ascending", "descending"] = "ascending"
    max_bytes: int = 1 << 20


@router.post("/lsb")
def image_lsb(req: LSBRequest):
    sf = _require_image(req.file_id)
    params = lsb.LSBParams(
        channels=req.channels, bit_planes=req.bit_planes, traversal=req.traversal,
        channel_mode=req.channel_mode, bit_order=req.bit_order,
        plane_order=req.plane_order, max_bytes=req.max_bytes,
    )
    try:
        return lsb.extract(sf.stored_path, params)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/lsb/save")
def image_lsb_save(req: LSBRequest):
    """Run the LSB extraction and store the raw bytes as a recovered payload."""
    sf = _require_image(req.file_id)
    params = lsb.LSBParams(
        channels=req.channels, bit_planes=req.bit_planes, traversal=req.traversal,
        channel_mode=req.channel_mode, bit_order=req.bit_order,
        plane_order=req.plane_order, max_bytes=req.max_bytes,
    )
    data = lsb.extract_raw(sf.stored_path, params)
    if not data:
        raise HTTPException(400, "LSB extraction produced no bytes")
    name = f"lsb_{'-'.join(req.channels)}_b{'-'.join(map(str, req.bit_planes))}.bin"
    out = storage.store_extracted(data, name, parent_id=sf.id,
                                  meta={"method": "image_lsb", "params": req.model_dump()})
    return {"file_id": out.id, "name": out.name, "size": out.size, "sha256": out.sha256,
            "detected_format": out.format}


# ---- Bitplanes --------------------------------------------------------------
@router.get("/bitplanes/overview/{file_id}")
def bitplane_overview(file_id: str):
    sf = _require_image(file_id)
    try:
        return bitplanes.overview(sf.stored_path)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/bitplanes/plane/{file_id}")
def bitplane_plane(file_id: str, channel: str, bit: int, invert: bool = False,
                   contrast: bool = True):
    sf = _require_image(file_id)
    try:
        data, meta = bitplanes.render_plane(sf.stored_path, channel, bit,
                                            invert=invert, contrast=contrast)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"image": _png_data_url(data), "meta": meta}


# ---- Channels ---------------------------------------------------------------
@router.get("/channels/histograms/{file_id}")
def channel_histograms(file_id: str):
    sf = _require_image(file_id)
    return channels.histograms(sf.stored_path)


@router.get("/channels/statistics/{file_id}")
def channel_statistics(file_id: str):
    sf = _require_image(file_id)
    return channels.statistics(sf.stored_path)


@router.get("/channels/isolate/{file_id}")
def channel_isolate(file_id: str, channel: str, grayscale: bool = True):
    sf = _require_image(file_id)
    try:
        data = channels.isolate_channel(sf.stored_path, channel, grayscale=grayscale)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"image": _png_data_url(data)}


class TransformRequest(BaseModel):
    file_id: str
    invert: bool = False
    grayscale: bool = False
    brightness: float = 0.0
    contrast: float = 1.0
    gamma: float = 1.0
    bit_mask: Optional[int] = None


@router.post("/channels/transform")
def channel_transform(req: TransformRequest):
    sf = _require_image(req.file_id)
    data = channels.transform(
        sf.stored_path, invert=req.invert, grayscale=req.grayscale,
        brightness=req.brightness, contrast=req.contrast, gamma=req.gamma,
        bit_mask=req.bit_mask,
    )
    return {"image": _png_data_url(data)}


@router.get("/channels/difference/{file_id}")
def channel_diff(file_id: str, channel_a: str, channel_b: str, amplify: int = 1):
    sf = _require_image(file_id)
    try:
        data = channels.channel_difference(sf.stored_path, channel_a, channel_b, amplify=amplify)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"image": _png_data_url(data)}


# ---- Format-specific --------------------------------------------------------
@router.get("/format/{file_id}")
def image_format(file_id: str):
    sf = _require_image(file_id)
    fmt = sf.format
    try:
        if fmt == "png":
            return {"format": "png", "analysis": png.analyse(sf.stored_path)}
        if fmt == "jpeg":
            return {"format": "jpeg", "analysis": jpeg.analyse(sf.stored_path)}
        if fmt == "bmp":
            return {"format": "bmp", "analysis": bmp.analyse(sf.stored_path)}
        if fmt == "gif":
            return {"format": "gif", "analysis": gif.analyse(sf.stored_path)}
        if fmt == "tiff":
            return {"format": "tiff", "analysis": tiff_webp.analyse_tiff(sf.stored_path)}
        if fmt == "webp":
            return {"format": "webp", "analysis": tiff_webp.analyse_webp(sf.stored_path)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    raise HTTPException(400, f"No structural parser for format '{fmt}'")


@router.get("/gif/frame/{file_id}")
def gif_frame(file_id: str, index: int, save: bool = False):
    sf = _require_image(file_id)
    try:
        data = gif.extract_frame(sf.stored_path, index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if save:
        out = storage.store_extracted(data, f"gif_frame_{index}.png", parent_id=sf.id,
                                      meta={"method": "gif_frame", "index": index})
        return {"file_id": out.id, "name": out.name, "image": _png_data_url(data)}
    return {"image": _png_data_url(data)}


# ---- External tools ---------------------------------------------------------
@router.post("/tools/zsteg")
def tool_zsteg(file_id: str, all_methods: bool = True):
    sf = _require_image(file_id)
    try:
        return ti.run_zsteg(sf.stored_path, all_methods=all_methods)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))


@router.post("/tools/zsteg/extract")
def tool_zsteg_extract(file_id: str, method: str):
    sf = _require_image(file_id)
    try:
        raw, info = ti.zsteg_extract(sf.stored_path, method)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
    if not raw:
        return {"ok": False, "info": info}
    out = storage.store_extracted(raw, f"zsteg_{method.replace(',', '_')}.bin",
                                  parent_id=sf.id, meta={"method": "zsteg", "zsteg_method": method})
    return {"ok": True, "file_id": out.id, "name": out.name, "size": out.size, "info": info}


@router.post("/tools/steghide")
def tool_steghide(file_id: str, passphrase: str = ""):
    sf = _require_image(file_id)
    try:
        payload, info = ti.steghide_extract_payload(sf.stored_path, passphrase)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
    if payload:
        out = storage.store_extracted(payload, "steghide_payload.bin", parent_id=sf.id,
                                      meta={"method": "steghide"})
        info["file_id"] = out.id
    return info


@router.post("/tools/stegseek")
def tool_stegseek(file_id: str, wordlist: Optional[str] = None):
    sf = _require_image(file_id)
    try:
        payload, info = ti.run_stegseek(sf.stored_path, wordlist)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
    if payload:
        out = storage.store_extracted(payload, "stegseek_payload.bin", parent_id=sf.id,
                                      meta={"method": "stegseek"})
        info["file_id"] = out.id
    return info


@router.post("/tools/outguess")
def tool_outguess(file_id: str, key: str = ""):
    sf = _require_image(file_id)
    try:
        payload, info = ti.run_outguess(sf.stored_path, key)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
    if payload:
        out = storage.store_extracted(payload, "outguess_payload.bin", parent_id=sf.id,
                                      meta={"method": "outguess"})
        info["file_id"] = out.id
    return info


@router.post("/tools/exiftool")
def tool_exiftool(file_id: str):
    sf = _require_image(file_id)
    try:
        return ti.run_exiftool(sf.stored_path)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))


@router.post("/tools/binwalk")
def tool_binwalk(file_id: str):
    sf = _require_image(file_id)
    try:
        return ti.run_binwalk(sf.stored_path)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))


@router.post("/tools/ocr")
def tool_ocr(file_id: str, lang: str = "eng"):
    sf = _require_image(file_id)
    try:
        return ti.run_ocr(sf.stored_path, lang)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
