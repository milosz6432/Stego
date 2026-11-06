"""Video container / stream inspection via ffprobe."""
from __future__ import annotations

import json
from pathlib import Path

from ...core import tools
from ...core.tools import ToolNotAvailable, run_tool


def probe(path: str | Path) -> dict:
    if not tools.available("ffprobe"):
        raise ToolNotAvailable("ffprobe")
    args = ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    res = run_tool("ffprobe", args, timeout=60)
    if not res.ok:
        return {"ok": False, "error": res.stderr[:500], "command": res.to_dict()}
    try:
        data = json.loads(res.stdout)
    except Exception as e:
        return {"ok": False, "error": f"Could not parse ffprobe output: {e}"}

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video_streams, audio_streams, other = [], [], []
    for s in streams:
        entry = {
            "index": s.get("index"),
            "codec_name": s.get("codec_name"),
            "codec_type": s.get("codec_type"),
            "codec_long_name": s.get("codec_long_name"),
            "tags": s.get("tags", {}),
        }
        if s.get("codec_type") == "video":
            entry.update({
                "width": s.get("width"), "height": s.get("height"),
                "pix_fmt": s.get("pix_fmt"),
                "avg_frame_rate": s.get("avg_frame_rate"),
                "r_frame_rate": s.get("r_frame_rate"),
                "nb_frames": s.get("nb_frames"),
                "bit_rate": s.get("bit_rate"),
                "duration": s.get("duration"),
            })
            video_streams.append(entry)
        elif s.get("codec_type") == "audio":
            entry.update({
                "sample_rate": s.get("sample_rate"),
                "channels": s.get("channels"),
                "channel_layout": s.get("channel_layout"),
                "bit_rate": s.get("bit_rate"),
                "duration": s.get("duration"),
            })
            audio_streams.append(entry)
        else:
            other.append(entry)

    return {
        "ok": True,
        "format": {
            "format_name": fmt.get("format_name"),
            "format_long_name": fmt.get("format_long_name"),
            "duration": fmt.get("duration"),
            "size": fmt.get("size"),
            "bit_rate": fmt.get("bit_rate"),
            "nb_streams": fmt.get("nb_streams"),
            "tags": fmt.get("tags", {}),
        },
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "other_streams": other,
        "command": res.to_dict(),
    }


def frame_rate(path: str | Path) -> float:
    info = probe(path)
    if not info.get("ok") or not info["video_streams"]:
        return 0.0
    rate = info["video_streams"][0].get("avg_frame_rate") or "0/1"
    try:
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 0.0
    except Exception:
        return 0.0
