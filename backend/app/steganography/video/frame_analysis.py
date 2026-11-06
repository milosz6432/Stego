"""Frame-to-frame difference analysis.

Computes per-frame-pair difference magnitude to flag frames that change in
unusual ways (a single frame carrying hidden pixels often differs sharply
from its neighbours). Produces both a numeric series and a difference image.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image


def difference_series(frame_paths: list[str | Path]) -> dict:
    diffs = []
    prev = None
    for i, fp in enumerate(frame_paths):
        arr = np.asarray(Image.open(fp).convert("RGB"), dtype=np.int16)
        if prev is not None and prev.shape == arr.shape:
            d = np.abs(arr - prev)
            diffs.append({
                "frame": i,
                "mean_diff": round(float(d.mean()), 4),
                "max_diff": int(d.max()),
                "changed_pixels": int(np.count_nonzero(d.sum(axis=2))),
            })
        prev = arr
    mean_series = [d["mean_diff"] for d in diffs]
    anomalies = []
    if mean_series:
        arr = np.array(mean_series)
        mu, sigma = arr.mean(), arr.std() + 1e-9
        for d in diffs:
            z = (d["mean_diff"] - mu) / sigma
            if z > 3:
                anomalies.append({"frame": d["frame"], "z_score": round(float(z), 2)})
    return {"frame_count": len(frame_paths), "differences": diffs, "anomalies": anomalies}


def difference_image(frame_a: str | Path, frame_b: str | Path, amplify: int = 1) -> bytes:
    a = np.asarray(Image.open(frame_a).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(frame_b).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        raise ValueError("Frame sizes differ")
    d = np.clip(np.abs(a - b) * max(1, amplify), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(d, "RGB").save(buf, format="PNG")
    return buf.getvalue()
