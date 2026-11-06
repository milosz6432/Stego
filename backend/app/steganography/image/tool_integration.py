"""Integration wrappers for external steganography/forensics tools.

Every wrapper returns a structured dict including the exact command executed
and captured stdout/stderr. If the external command fails we report the
failure honestly — never a fabricated success.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from ...core import tools
from ...core.tools import ToolNotAvailable, run_tool, run_tool_binary
from ...core.util import b64, printable_ratio


def _tool_envelope(res) -> dict:
    d = res.to_dict()
    return d


# ---- zsteg (PNG/BMP) --------------------------------------------------------
def run_zsteg(path: str | Path, *, all_methods: bool = True, extra: Optional[list[str]] = None) -> dict:
    if not tools.available("zsteg"):
        raise ToolNotAvailable("zsteg")
    args: list[str] = []
    if all_methods:
        args.append("-a")
    if extra:
        args.extend(extra)
    args.append(str(path))
    res = run_tool("zsteg", args, timeout=180)
    # Parse zsteg's "channel .. : value" findings lines
    findings = []
    for line in res.stdout.splitlines():
        line = line.rstrip()
        if not line or line.startswith("["):
            continue
        if ".." in line and ":" in line:
            method, _, value = line.partition(":")
            findings.append({"method": method.strip(), "value": value.strip()})
    return {"command": _tool_envelope(res), "findings": findings,
            "finding_count": len(findings), "ok": res.ok}


def zsteg_extract(path: str | Path, method: str) -> tuple[bytes, dict]:
    """Extract a specific zsteg payload, e.g. method='b1,rgb,lsb,xy'."""
    if not tools.available("zsteg"):
        raise ToolNotAvailable("zsteg")
    res, raw = run_tool_binary("zsteg", ["-E", method, str(path)], timeout=180)
    return raw, {"command": _tool_envelope(res), "method": method, "bytes": len(raw)}


# ---- steghide (JPEG/BMP/WAV/AU) --------------------------------------------
def run_steghide_info(path: str | Path) -> dict:
    if not tools.available("steghide"):
        raise ToolNotAvailable("steghide")
    res = run_tool("steghide", ["info", "--", str(path)], timeout=60, input_bytes=b"n\n")
    return {"command": _tool_envelope(res), "ok": res.ok}


def steghide_extract(path: str | Path, passphrase: str = "") -> dict:
    if not tools.available("steghide"):
        raise ToolNotAvailable("steghide")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "steghide_out.bin")
        args = ["extract", "-sf", str(path), "-xf", out, "-p", passphrase, "-f"]
        res = run_tool("steghide", args, timeout=60)
        payload = b""
        if res.ok and os.path.exists(out):
            payload = Path(out).read_bytes()
        return {
            "command": _tool_envelope(res),
            "ok": res.ok and len(payload) > 0,
            "extracted_bytes": len(payload),
            "payload_b64": b64(payload[:1 << 20]) if payload else None,
            "printable_ratio": round(printable_ratio(payload), 3) if payload else None,
        }, payload  # type: ignore[return-value]


def steghide_extract_payload(path: str | Path, passphrase: str = "") -> tuple[bytes, dict]:
    info, payload = steghide_extract(path, passphrase)  # type: ignore[misc]
    return payload, info


# ---- stegseek (crack steghide passphrase) ----------------------------------
def run_stegseek(path: str | Path, wordlist: Optional[str] = None) -> tuple[bytes, dict]:
    if not tools.available("stegseek"):
        raise ToolNotAvailable("stegseek")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "stegseek_out.bin")
        args = [str(path)]
        if wordlist:
            args.append(wordlist)
        args.extend(["-xf", out, "-f"])
        res = run_tool("stegseek", args, timeout=300)
        passphrase = None
        m = re.search(r'passphrase\s*:\s*"([^"]*)"', res.stdout)
        if m:
            passphrase = m.group(1)
        payload = Path(out).read_bytes() if os.path.exists(out) else b""
        return payload, {
            "command": _tool_envelope(res),
            "ok": res.ok and len(payload) > 0,
            "passphrase": passphrase,
            "extracted_bytes": len(payload),
            "payload_b64": b64(payload[:1 << 20]) if payload else None,
        }


# ---- outguess (JPEG) --------------------------------------------------------
def run_outguess(path: str | Path, key: str = "") -> tuple[bytes, dict]:
    if not tools.available("outguess"):
        raise ToolNotAvailable("outguess")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "outguess_out.bin")
        args = ["-r"]
        if key:
            args.extend(["-k", key])
        args.extend([str(path), out])
        res = run_tool("outguess", args, timeout=120)
        payload = Path(out).read_bytes() if os.path.exists(out) else b""
        return payload, {
            "command": _tool_envelope(res),
            "ok": res.ok and len(payload) > 0,
            "extracted_bytes": len(payload),
            "payload_b64": b64(payload[:1 << 20]) if payload else None,
            "printable_ratio": round(printable_ratio(payload), 3) if payload else None,
        }


# ---- exiftool ---------------------------------------------------------------
def run_exiftool(path: str | Path) -> dict:
    if not tools.available("exiftool"):
        raise ToolNotAvailable("exiftool")
    res = run_tool("exiftool", ["-a", "-u", "-g1", "-json", str(path)], timeout=60)
    import json
    metadata = None
    try:
        parsed = json.loads(res.stdout)
        metadata = parsed[0] if parsed else {}
    except Exception:
        metadata = None
    return {"command": _tool_envelope(res), "metadata": metadata, "ok": res.ok}


# ---- binwalk ----------------------------------------------------------------
def run_binwalk(path: str | Path) -> dict:
    if not tools.available("binwalk"):
        raise ToolNotAvailable("binwalk")
    # -B: signature scan only (no entropy/opcode passes), much faster.
    res = run_tool("binwalk", ["-B", "--term", str(path)], timeout=60)
    signatures = []
    for line in res.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            signatures.append({"decimal_offset": int(parts[0]), "hex_offset": parts[1],
                               "description": parts[2]})
    return {"command": _tool_envelope(res), "signatures": signatures,
            "signature_count": len(signatures), "ok": res.ok}


# ---- tesseract OCR ----------------------------------------------------------
def run_ocr(path: str | Path, lang: str = "eng") -> dict:
    if not tools.available("tesseract"):
        raise ToolNotAvailable("tesseract")
    res = run_tool("tesseract", [str(path), "stdout", "-l", lang], timeout=60)
    text = res.stdout.strip()
    return {"command": _tool_envelope(res), "text": text, "ok": res.ok and bool(text)}
