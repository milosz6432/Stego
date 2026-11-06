"""Audio analysis API — the dedicated audio steganography workspace backend."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.storage import storage
from ..core.tools import ToolNotAvailable
from ..core.util import b64
from ..steganography.audio import (
    advanced,
    dtmf,
    fft,
    morse,
    pcm_lsb,
    segment,
    spectrogram as spec_mod,
    sstv,
    waveform,
)
from ..steganography.audio.loader import load_audio
from ..steganography.image import tool_integration as ti

router = APIRouter(prefix="/api/audio", tags=["audio"])


def _require(file_id: str):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    return sf


def _png_url(data: bytes) -> str:
    return "data:image/png;base64," + b64(data)


@router.get("/info/{file_id}")
def info(file_id: str):
    sf = _require(file_id)
    try:
        a = load_audio(sf.stored_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "sample_rate": a.sample_rate,
        "channels": a.channels,
        "frames": a.n_frames,
        "duration": a.duration,
        "format": a.source_format,
        "subtype": a.subtype,
        "is_lossless_pcm": a.is_lossless_pcm,
        "sample_width_bits": a.sample_width_bits,
        "transformations": a.transformations,
    }


@router.get("/waveform/{file_id}")
def get_waveform(file_id: str, buckets: int = 2000,
                 start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return waveform.waveform(sf.stored_path, buckets=buckets, start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/statistics/{file_id}")
def get_statistics(file_id: str, start: Optional[float] = None, end: Optional[float] = None,
                   silence_db: float = -50.0):
    sf = _require(file_id)
    return waveform.statistics(sf.stored_path, start=start, end=end, silence_db=silence_db)


class SpectrogramRequest(BaseModel):
    file_id: str
    channel: int = 0
    n_fft: int = 1024
    hop: Optional[int] = None
    window: str = "hann"
    overlap: Optional[float] = None
    scale: Literal["linear", "log", "mel"] = "linear"
    f_min: float = 0.0
    f_max: Optional[float] = None
    top_db: float = 80.0
    n_mels: int = 256
    colormap: str = "magma"
    start: Optional[float] = None
    end: Optional[float] = None


@router.post("/spectrogram")
def spectrogram(req: SpectrogramRequest):
    sf = _require(req.file_id)
    try:
        png, meta = spec_mod.spectrogram_image(
            sf.stored_path, cmap=req.colormap, channel=req.channel, n_fft=req.n_fft,
            hop=req.hop, window=req.window, overlap=req.overlap, scale=req.scale,
            f_min=req.f_min, f_max=req.f_max, top_db=req.top_db, n_mels=req.n_mels,
            start=req.start, end=req.end,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"image": _png_url(png), "meta": meta}


@router.get("/fft/{file_id}")
def get_fft(file_id: str, channel: int = 0, window: str = "hann",
            start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return fft.spectrum(sf.stored_path, channel=channel, window=window, start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/fft/compare/{file_id}")
def fft_compare(file_id: str, start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    return fft.channel_comparison(sf.stored_path, start=start, end=end)


# ---- PCM LSB ----------------------------------------------------------------
class PCMRequest(BaseModel):
    file_id: str
    channels: list[int] = Field(default_factory=lambda: [0])
    bit_planes: list[int] = Field(default_factory=lambda: [0])
    channel_mode: Literal["interleave", "sequential"] = "interleave"
    bit_order: Literal["msb", "lsb"] = "msb"
    max_bytes: int = 1 << 20


@router.post("/pcm-lsb")
def pcm_lsb_extract(req: PCMRequest):
    sf = _require(req.file_id)
    params = pcm_lsb.PCMParams(channels=req.channels, bit_planes=req.bit_planes,
                               channel_mode=req.channel_mode, bit_order=req.bit_order,
                               max_bytes=req.max_bytes)
    try:
        return pcm_lsb.extract(sf.stored_path, params)
    except pcm_lsb.NotLosslessPCM as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/pcm-lsb/save")
def pcm_lsb_save(req: PCMRequest):
    sf = _require(req.file_id)
    params = pcm_lsb.PCMParams(channels=req.channels, bit_planes=req.bit_planes,
                               channel_mode=req.channel_mode, bit_order=req.bit_order,
                               max_bytes=req.max_bytes)
    try:
        data = pcm_lsb.extract_raw(sf.stored_path, params)
    except pcm_lsb.NotLosslessPCM as e:
        raise HTTPException(422, str(e))
    if not data:
        raise HTTPException(400, "No bytes extracted")
    out = storage.store_extracted(data, f"pcm_lsb_ch{'-'.join(map(str, req.channels))}.bin",
                                  parent_id=sf.id, meta={"method": "pcm_lsb", "params": req.model_dump()})
    return {"file_id": out.id, "name": out.name, "size": out.size, "sha256": out.sha256,
            "detected_format": out.format}


# ---- Advanced ---------------------------------------------------------------
@router.get("/phase/{file_id}")
def phase(file_id: str, channel: int = 0, n_fft: int = 1024,
          start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return advanced.phase_analysis(sf.stored_path, channel=channel, n_fft=n_fft,
                                       start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/echo/{file_id}")
def echo(file_id: str, channel: int = 0, max_delay_ms: float = 50.0,
         start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return advanced.echo_analysis(sf.stored_path, channel=channel,
                                      max_delay_ms=max_delay_ms, start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/stereo/{file_id}")
def stereo(file_id: str, start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    return advanced.stereo_analysis(sf.stored_path, start=start, end=end)


@router.get("/zero-crossing/{file_id}")
def zero_crossing(file_id: str, channel: int = 0, window_ms: float = 20.0,
                  start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return advanced.zero_crossing(sf.stored_path, channel=channel, window_ms=window_ms,
                                      start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/pattern/{file_id}")
def pattern(file_id: str, channel: int = 0):
    sf = _require(file_id)
    try:
        return advanced.pattern_scan(sf.stored_path, channel=channel)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- Decoders ---------------------------------------------------------------
@router.get("/dtmf/{file_id}")
def decode_dtmf(file_id: str, channel: int = 0,
                start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return dtmf.decode(sf.stored_path, channel=channel, start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/morse/{file_id}")
def decode_morse(file_id: str, channel: int = 0,
                 start: Optional[float] = None, end: Optional[float] = None):
    sf = _require(file_id)
    try:
        return morse.decode(sf.stored_path, channel=channel, start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/sstv/{file_id}")
def detect_sstv(file_id: str):
    sf = _require(file_id)
    return sstv.detect(sf.stored_path)


# ---- Segment export + external tools ---------------------------------------
@router.post("/segment/export")
def export_segment(file_id: str, start: Optional[float] = None, end: Optional[float] = None,
                   channel: Optional[int] = None):
    sf = _require(file_id)
    data, meta = segment.export_segment(sf.stored_path, start, end, channel=channel)
    out = storage.store_extracted(data, f"segment_{meta['start_time']:.2f}-{meta['end_time']:.2f}.wav",
                                  parent_id=sf.id, meta={"method": "segment_export", **meta})
    return {"file_id": out.id, "name": out.name, "meta": meta}


@router.post("/tools/steghide")
def tool_steghide(file_id: str, passphrase: str = ""):
    sf = _require(file_id)
    try:
        payload, info = ti.steghide_extract_payload(sf.stored_path, passphrase)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
    if payload:
        out = storage.store_extracted(payload, "steghide_audio_payload.bin", parent_id=sf.id,
                                      meta={"method": "steghide"})
        info["file_id"] = out.id
    return info


@router.post("/tools/stegseek")
def tool_stegseek(file_id: str, wordlist: Optional[str] = None):
    sf = _require(file_id)
    try:
        payload, info = ti.run_stegseek(sf.stored_path, wordlist)
    except ToolNotAvailable as e:
        raise HTTPException(503, str(e))
    if payload:
        out = storage.store_extracted(payload, "stegseek_audio_payload.bin", parent_id=sf.id,
                                      meta={"method": "stegseek"})
        info["file_id"] = out.id
    return info
