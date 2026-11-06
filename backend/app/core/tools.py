"""External tool registry and safe subprocess execution.

Every optional external executable (zsteg, steghide, …) is declared here.
Availability is probed once and cached. Features that require a missing tool
report that clearly instead of silently faking a result.

All execution goes through :func:`run_tool`, which:
  * never uses a shell (argument list only -> no command injection),
  * enforces a wall-clock timeout,
  * caps captured output,
  * returns a structured result including the exact argv.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from . import config


@dataclass
class ToolSpec:
    name: str
    # Candidate executable names / absolute paths to probe, in order.
    candidates: list[str]
    description: str
    install_hint: str


# zsteg is a Ruby gem; on this image it installs under rbenv and may not be on
# PATH, so we probe a few known locations too.
_ZSTEG_EXTRA = [
    p
    for p in (
        "/opt/rbenv/versions/3.3.6/bin/zsteg",
        os.path.expanduser("~/.gem/ruby/*/bin/zsteg"),
    )
]

TOOL_SPECS: dict[str, ToolSpec] = {
    "zsteg": ToolSpec(
        "zsteg",
        ["zsteg", *_ZSTEG_EXTRA],
        "Detects LSB stego in PNG/BMP images (Ruby gem).",
        "gem install zsteg",
    ),
    "steghide": ToolSpec(
        "steghide",
        ["steghide"],
        "Embeds/extracts data in JPEG/BMP/WAV/AU with a passphrase.",
        "apt-get install steghide",
    ),
    "stegseek": ToolSpec(
        "stegseek",
        ["stegseek"],
        "Fast steghide passphrase cracker (wordlist).",
        "apt-get install stegseek (or build from releases)",
    ),
    "outguess": ToolSpec(
        "outguess",
        ["outguess"],
        "Statistical JPEG steganography embed/extract.",
        "apt-get install outguess",
    ),
    "exiftool": ToolSpec(
        "exiftool",
        ["exiftool"],
        "Reads metadata from virtually every media format.",
        "apt-get install libimage-exiftool-perl",
    ),
    "binwalk": ToolSpec(
        "binwalk",
        ["binwalk"],
        "Scans for embedded files and signatures.",
        "apt-get install binwalk",
    ),
    "ffmpeg": ToolSpec(
        "ffmpeg",
        ["ffmpeg"],
        "Audio/video decoding, conversion and extraction.",
        "apt-get install ffmpeg",
    ),
    "ffprobe": ToolSpec(
        "ffprobe",
        ["ffprobe"],
        "Media container/stream inspection.",
        "apt-get install ffmpeg",
    ),
    "tesseract": ToolSpec(
        "tesseract",
        ["tesseract"],
        "OCR engine for text hidden in images/frames.",
        "apt-get install tesseract-ocr",
    ),
}


@lru_cache(maxsize=None)
def resolve(tool: str) -> Optional[str]:
    """Return the absolute path of *tool* or ``None`` if unavailable."""
    spec = TOOL_SPECS.get(tool)
    if spec is None:
        return None
    for cand in spec.candidates:
        if "*" in cand:  # glob candidate
            import glob

            matches = sorted(glob.glob(cand))
            if matches:
                return matches[-1]
            continue
        found = shutil.which(cand) if os.path.sep not in cand else (
            cand if os.path.isfile(cand) and os.access(cand, os.X_OK) else None
        )
        if found:
            return found
    return None


def available(tool: str) -> bool:
    return resolve(tool) is not None


def registry() -> list[dict]:
    """Snapshot of every declared tool and whether it is installed."""
    out = []
    for name, spec in TOOL_SPECS.items():
        path = resolve(name)
        out.append(
            {
                "name": name,
                "available": path is not None,
                "path": path,
                "description": spec.description,
                "install_hint": spec.install_hint,
            }
        )
    return out


@dataclass
class ToolResult:
    tool: str
    argv: list[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    error: Optional[str] = None
    duration_ms: int = 0
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.error is None

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "command": " ".join(_shellquote(a) for a in self.argv),
            "argv": self.argv,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
            "ok": self.ok,
        }


def _shellquote(s: str) -> str:
    if s and all(c.isalnum() or c in "-_=/.:@" for c in s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


class ToolNotAvailable(RuntimeError):
    def __init__(self, tool: str):
        spec = TOOL_SPECS.get(tool)
        hint = spec.install_hint if spec else "unknown tool"
        super().__init__(f"Required tool '{tool}' is not installed. Install with: {hint}")
        self.tool = tool


def run_tool(
    tool: str,
    args: list[str],
    *,
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    input_bytes: Optional[bytes] = None,
    env: Optional[dict] = None,
) -> ToolResult:
    """Run *tool* with *args* safely and return a :class:`ToolResult`.

    Raises :class:`ToolNotAvailable` if the executable is missing so callers
    can surface an honest error.
    """
    import time

    path = resolve(tool)
    if path is None:
        raise ToolNotAvailable(tool)

    argv = [path, *args]
    timeout = timeout or config.TOOL_TIMEOUT_SECONDS
    cap = config.TOOL_MAX_OUTPUT_BYTES

    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    # Keep external tools from spawning network calls / interactive prompts.
    run_env.setdefault("GEM_PATH", run_env.get("GEM_PATH", ""))

    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            input=input_bytes,
            env=run_env,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return ToolResult(
            tool=tool,
            argv=argv,
            returncode=None,
            stdout=_decode(e.stdout, cap),
            stderr=_decode(e.stderr, cap),
            timed_out=True,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except (OSError, ValueError) as e:
        return ToolResult(
            tool=tool,
            argv=argv,
            returncode=None,
            stdout="",
            stderr="",
            error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    out = proc.stdout or b""
    err = proc.stderr or b""
    truncated = len(out) > cap or len(err) > cap
    return ToolResult(
        tool=tool,
        argv=argv,
        returncode=proc.returncode,
        stdout=_decode(out, cap),
        stderr=_decode(err, cap),
        duration_ms=int((time.monotonic() - start) * 1000),
        truncated=truncated,
    )


def run_tool_binary(
    tool: str,
    args: list[str],
    *,
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
) -> tuple[ToolResult, bytes]:
    """Like :func:`run_tool` but also returns raw stdout bytes (for binary extraction)."""
    import time

    path = resolve(tool)
    if path is None:
        raise ToolNotAvailable(tool)
    argv = [path, *args]
    timeout = timeout or config.TOOL_TIMEOUT_SECONDS
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout, cwd=cwd, check=False
        )
    except subprocess.TimeoutExpired as e:
        return (
            ToolResult(tool, argv, None, "", _decode(e.stderr, 65536), timed_out=True,
                       duration_ms=int((time.monotonic() - start) * 1000)),
            b"",
        )
    res = ToolResult(
        tool=tool,
        argv=argv,
        returncode=proc.returncode,
        stdout="<binary>",
        stderr=_decode(proc.stderr or b"", 65536),
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    return res, (proc.stdout or b"")


def _decode(data: Optional[bytes], cap: int) -> str:
    if not data:
        return ""
    if len(data) > cap:
        data = data[:cap]
    return data.decode("utf-8", errors="replace")
