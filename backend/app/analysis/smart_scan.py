"""Smart Scan engine.

Format-aware orchestration that runs the techniques that actually apply to the
uploaded file, tests a *bounded* set of extraction configurations (never a
blind combinatorial sweep), inspects what comes out, scores each finding with
explanations, stores promising payloads, and returns a ranked list.

Depth levels:
  * quick    — the few highest-value checks, fast.
  * standard — adds common LSB/channel configs + external detectors.
  * deep     — adds more bit-plane/traversal combinations and slower tools,
               still within hard caps.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Literal, Optional

from ..core import tools
from ..core.job_manager import ProgressHandle
from ..core.storage import storage
from ..core.util import printable_ratio
from ..extraction import payload as payload_mod
from ..extraction import signatures
from ..steganography.audio import dtmf, morse, pcm_lsb, sstv
from ..steganography.audio.advanced import stereo_analysis
from ..steganography.image import bitplanes, lsb
from ..steganography.image import tool_integration as ti
from .scoring import Finding, rank, score_payload

Depth = Literal["quick", "standard", "deep"]
_STORE_THRESHOLD = 25.0     # only persist payloads that score at least this


def _store_if_good(finding: Finding, data: bytes, parent_id: str, name: str) -> None:
    score_payload(finding, data)
    if finding.score >= _STORE_THRESHOLD and data:
        out = storage.store_extracted(data, name, parent_id=parent_id,
                                      meta={"method": finding.method, "source": "smart_scan"})
        finding.file_id = out.id
        finding.details["stored_size"] = out.size
        finding.details["detected_format"] = out.format


# ---- image LSB config sets --------------------------------------------------
def _image_lsb_configs(depth: Depth) -> list[dict]:
    base = [
        {"channels": ["R", "G", "B"], "bit_planes": [0], "channel_mode": "interleave",
         "bit_order": "msb", "traversal": "row"},
    ]
    if depth == "quick":
        return base
    standard = base + [
        {"channels": ["R"], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "msb", "traversal": "row"},
        {"channels": ["G"], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "msb", "traversal": "row"},
        {"channels": ["B"], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "msb", "traversal": "row"},
        {"channels": ["A"], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "msb", "traversal": "row"},
        {"channels": ["R", "G", "B"], "bit_planes": [0], "channel_mode": "interleave", "bit_order": "lsb", "traversal": "row"},
        {"channels": ["R", "G", "B"], "bit_planes": [0], "channel_mode": "interleave", "bit_order": "msb", "traversal": "column"},
    ]
    if depth == "standard":
        return standard
    deep = standard + [
        {"channels": ["R", "G", "B"], "bit_planes": [0, 1], "channel_mode": "interleave", "bit_order": "msb", "traversal": "row"},
        {"channels": ["R", "G", "B"], "bit_planes": [1], "channel_mode": "interleave", "bit_order": "msb", "traversal": "row"},
        {"channels": ["R"], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "lsb", "traversal": "column"},
        {"channels": ["R", "G", "B"], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "msb", "traversal": "row"},
    ]
    return deep


def scan_image(sf, depth: Depth, p: ProgressHandle) -> list[Finding]:
    findings: list[Finding] = []
    path = sf.stored_path
    data = Path(path).read_bytes()

    # 1) trailing data / appended payload (highest-value, cheap)
    p.update(0.1, "Checking for appended/trailing data")
    tr = payload_mod.trailing_data(path, sf.format)
    if tr:
        f = Finding("Data appended after image end", "trailing_data",
                    details={"size": tr["size"], "signatures": tr["signatures"]})
        f.add(30, f"{tr['size']} bytes found after the format's logical end")
        _store_if_good(f, tr["data"], sf.id, f"trailing_{sf.format}.bin")
        findings.append(f)

    # 2) generic signature carve over the whole file
    p.update(0.2, "Carving embedded files by signature")
    carved = signatures.carve(data, max_files=20)
    for c in carved:
        if c["offset"] == 0 and c["name"].lower() == sf.format.upper().lower():
            continue  # the container itself
        f = Finding(f"Embedded {c['name']} at offset {c['offset']}", "signature_carve",
                    details={"offset": c["offset"], "size": c["size"]})
        f.add(25, f"carved a complete {c['name']} ({c['size']} bytes)")
        _store_if_good(f, c["data"], sf.id, f"carved_{c['name']}_{c['offset']}.{c['ext']}")
        findings.append(f)

    # 3) LSB configurations (bounded)
    configs = _image_lsb_configs(depth)
    for i, cfg in enumerate(configs):
        p.update(0.3 + 0.4 * i / len(configs), f"LSB config {i+1}/{len(configs)}")
        try:
            params = lsb.LSBParams(max_bytes=256 * 1024, **cfg)
            raw = lsb.extract_raw(path, params)
        except Exception:
            continue
        if not raw or printable_ratio(raw[:256]) < 0.2 and not signatures.scan(raw[:64]):
            # quick reject obviously-noise results unless a signature appears
            quick = signatures.scan(raw[:64], max_results=3)
            if not quick:
                continue
        label = f"LSB {'/'.join(cfg['channels'])} plane {cfg['bit_planes']} " \
                f"{cfg['channel_mode']}/{cfg['bit_order']}/{cfg['traversal']}"
        f = Finding(label, "image_lsb", details={"config": cfg})
        _store_if_good(f, raw, sf.id, f"lsb_{i}.bin")
        if f.score > 0:
            findings.append(f)

    # 4) bit-plane structure overview (visual anomaly cue, not extraction)
    if depth in ("standard", "deep"):
        p.update(0.75, "Scoring bit-plane structure")
        try:
            ov = bitplanes.overview(path)
            for plane in ov.get("suspicious", [])[:4]:
                f = Finding(f"Structured low bit-plane: {plane['channel']} bit {plane['bit']}",
                            "bitplane_structure", details=plane)
                f.add(15 * plane["structure_score"], "low bit-plane shows non-random structure")
                f.add(5, "inspect this plane visually in the Bitplane viewer")
                findings.append(f)
        except Exception:
            pass

    # 5) external tools
    p.update(0.85, "Running external tools")
    if sf.format in ("png", "bmp") and tools.available("zsteg"):
        try:
            z = ti.run_zsteg(path, all_methods=(depth == "deep"))
            if z["findings"]:
                f = Finding(f"zsteg reported {len(z['findings'])} finding(s)", "zsteg",
                            details={"findings": z["findings"][:30]})
                f.add(20, "zsteg detected structured LSB data")
                findings.append(f)
        except Exception:
            pass
    if depth == "deep" and sf.format in ("jpeg", "bmp") and tools.available("steghide"):
        try:
            pl, info = ti.steghide_extract_payload(path, "")
            if pl:
                f = Finding("steghide extracted a payload (empty passphrase)", "steghide")
                _store_if_good(f, pl, sf.id, "steghide_payload.bin")
                findings.append(f)
        except Exception:
            pass
    if depth == "deep" and sf.format == "jpeg" and tools.available("outguess"):
        try:
            pl, info = ti.run_outguess(path, "")
            if pl:
                f = Finding("outguess extracted a payload", "outguess")
                _store_if_good(f, pl, sf.id, "outguess_payload.bin")
                findings.append(f)
        except Exception:
            pass

    # 6) metadata
    if tools.available("exiftool"):
        try:
            meta = ti.run_exiftool(path)
            md = meta.get("metadata") or {}
            text_blob = " ".join(str(v) for v in md.values())
            from ..core.util import find_interesting
            interesting = find_interesting(text_blob.encode("utf-8", "replace"))
            if interesting["flags"]:
                f = Finding("Flag-like token in metadata", "exiftool",
                            details={"flags": interesting["flags"]})
                f.add(45, f"metadata contains {interesting['flags'][:2]}")
                findings.append(f)
        except Exception:
            pass

    return findings


def scan_audio(sf, depth: Depth, p: ProgressHandle) -> list[Finding]:
    findings: list[Finding] = []
    path = sf.stored_path

    # carve on raw bytes
    p.update(0.1, "Carving embedded files")
    data = Path(path).read_bytes()
    for c in signatures.carve(data, max_files=10):
        if c["offset"] == 0:
            continue
        f = Finding(f"Embedded {c['name']} at offset {c['offset']}", "signature_carve",
                    details={"offset": c["offset"], "size": c["size"]})
        f.add(25, f"carved a complete {c['name']}")
        _store_if_good(f, c["data"], sf.id, f"carved_{c['name']}_{c['offset']}.{c['ext']}")
        findings.append(f)

    # PCM-LSB (only if lossless)
    p.update(0.3, "Testing PCM sample LSB")
    configs = [{"channels": [0], "bit_planes": [0], "channel_mode": "interleave", "bit_order": "msb"}]
    if depth != "quick":
        configs += [
            {"channels": [1], "bit_planes": [0], "channel_mode": "sequential", "bit_order": "msb"},
            {"channels": [0, 1], "bit_planes": [0], "channel_mode": "interleave", "bit_order": "msb"},
            {"channels": [0], "bit_planes": [0], "channel_mode": "interleave", "bit_order": "lsb"},
        ]
    if depth == "deep":
        configs += [
            {"channels": [0], "bit_planes": [0, 1], "channel_mode": "interleave", "bit_order": "msb"},
            {"channels": [0], "bit_planes": [1], "channel_mode": "interleave", "bit_order": "msb"},
        ]
    for i, cfg in enumerate(configs):
        try:
            params = pcm_lsb.PCMParams(max_bytes=256 * 1024, **cfg)
            raw = pcm_lsb.extract_raw(path, params)
        except pcm_lsb.NotLosslessPCM:
            f = Finding("PCM-LSB not applicable (lossy source)", "pcm_lsb",
                        details={"note": "Decoded lossy audio has no meaningful sample LSBs"})
            findings.append(f)
            break
        except Exception:
            continue
        if not raw:
            continue
        f = Finding(f"PCM-LSB ch{cfg['channels']} plane {cfg['bit_planes']} "
                    f"{cfg['channel_mode']}/{cfg['bit_order']}", "pcm_lsb",
                    details={"config": cfg})
        _store_if_good(f, raw, sf.id, f"pcm_lsb_{i}.bin")
        if f.score > 0:
            findings.append(f)

    # decoders
    p.update(0.6, "Running DTMF / Morse decoders")
    try:
        d = dtmf.decode(path)
        if d["sequence"]:
            f = Finding(f"DTMF tones decoded: {d['sequence']}", "dtmf", details=d)
            f.add(35, f"recovered {d['count']} DTMF digit(s)")
            findings.append(f)
    except Exception:
        pass
    try:
        m = morse.decode(path)
        if m.get("text") and any(c.isalnum() for c in m["text"]):
            f = Finding(f"Morse decoded: {m['text']}", "morse", details=m)
            f.add(30, "recovered Morse-coded text")
            findings.append(f)
    except Exception:
        pass

    # stereo + sstv
    if depth != "quick":
        p.update(0.8, "Stereo + SSTV checks")
        try:
            st = stereo_analysis(path)
            if st.get("channels", 0) >= 2 and not st.get("identical_channels") and \
                    st.get("correlation", 0) > 0.99 and st.get("diff_rms", 0) > 1e-4:
                f = Finding("Stereo channels nearly identical with non-zero residual", "stereo",
                            details=st)
                f.add(15, "possible payload in the L-R difference")
                findings.append(f)
        except Exception:
            pass
    if depth == "deep":
        try:
            s = sstv.detect(path)
            if s.get("detected"):
                f = Finding("SSTV header detected", "sstv", details=s)
                f.add(25, f"VIS header(s): {s['headers']}")
                findings.append(f)
        except Exception:
            pass

    return findings


def scan_generic(sf, depth: Depth, p: ProgressHandle) -> list[Finding]:
    """For archives/documents/unknown data: signature carve + strings + metadata."""
    findings: list[Finding] = []
    data = Path(sf.stored_path).read_bytes()
    p.update(0.3, "Carving embedded files")
    for c in signatures.carve(data, max_files=20):
        if c["offset"] == 0 and c["size"] >= sf.size - 8:
            continue
        f = Finding(f"Embedded {c['name']} at offset {c['offset']}", "signature_carve",
                    details={"offset": c["offset"], "size": c["size"]})
        f.add(25, f"carved a complete {c['name']}")
        _store_if_good(f, c["data"], sf.id, f"carved_{c['name']}_{c['offset']}.{c['ext']}")
        findings.append(f)
    # whole-blob interesting text
    from ..core.util import find_interesting
    interesting = find_interesting(data)
    if interesting["flags"]:
        f = Finding("Flag-like token in file", "strings", details={"flags": interesting["flags"]})
        f.add(45, f"found {interesting['flags'][:3]}")
        findings.append(f)
    return findings


def run_smart_scan(file_id: str, depth: Depth, p: ProgressHandle) -> dict:
    sf = storage.require(file_id)
    p.update(0.05, f"Starting {depth} scan of {sf.name}")
    if sf.media_type == "image":
        findings = scan_image(sf, depth, p)
    elif sf.media_type == "audio":
        findings = scan_audio(sf, depth, p)
    else:
        findings = scan_generic(sf, depth, p)

    ranked = rank(findings)
    p.update(1.0, f"Scan complete — {len(ranked)} finding(s)")
    return {
        "file_id": file_id,
        "file_name": sf.name,
        "media_type": sf.media_type,
        "format": sf.format,
        "depth": depth,
        "finding_count": len(ranked),
        "findings": [f.to_dict() for f in ranked],
        "stored_payloads": [f.file_id for f in ranked if f.file_id],
    }
