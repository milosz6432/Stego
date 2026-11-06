# Architecture

STEGO LAB is a two-tier local application: a **FastAPI** backend that holds all
steganographic logic, and a **React + TypeScript** frontend that is a thin,
feature-complete client over the API. The frontend implements none of the core
algorithms.

## Backend layout

```
backend/app/
  main.py                      FastAPI app, routers, error handlers, CORS
  core/
    config.py                  paths, limits (env-overridable, no source edits)
    file_detection.py          magic-byte format/media-type detection
    storage.py                 immutable originals + working copies + recovered
                               payloads, disk-backed registry
    job_manager.py             background thread pool, progress, cancellation
    tools.py                   external-tool registry + safe subprocess runner
    util.py                    bit packing, hex dump, entropy, flag/text scan
  steganography/
    image/
      loader.py                Pillow→NumPy loader (bomb guard, channel meta)
      lsb.py                   configurable LSB/bit-plane extraction engine
      bitplanes.py             per-plane rendering + structure scoring
      channels.py              separation, histograms, χ², transforms, diffs
      png.py jpeg.py bmp.py    per-format structural parsers + trailing data
      gif.py tiff_webp.py
      tool_integration.py      zsteg/steghide/stegseek/outguess/exiftool/
                               binwalk/tesseract wrappers
    audio/
      loader.py                decode to float + (lossless) integer PCM
      waveform.py              peaks, RMS/peak/silence
      spectrogram.py           configurable STFT/mel → PNG (matplotlib LUTs)
      fft.py                   spectrum, peaks, harmonics, channel compare
      pcm_lsb.py               PCM sample-LSB engine (refuses lossy sources)
      advanced.py              phase, echo, stereo, zero-crossing, patterns
      dtmf.py morse.py sstv.py decoders (Goertzel / envelope / VIS detect)
      segment.py               time-range WAV export
    video/
      info.py                  ffprobe container/stream inspection
      frames.py                ffmpeg frame extraction + contact sheet
      frame_analysis.py        frame-difference series & anomaly detection
      audio_extraction.py      lossless audio-track extraction
  extraction/
    signatures.py              magic table + carver (headers + footers)
    payload.py                 trailing data, blob analysis, ZIP handling
  analysis/
    scoring.py                 transparent, explained heuristic scoring
    smart_scan.py              format-aware orchestration (quick/standard/deep)
  api/
    files.py jobs.py system.py image.py audio.py video.py
    extraction.py smart_scan.py
```

## Key design decisions

**Format detection is content-based.** CTF files are routinely mislabelled, so
every module decides what to do from magic bytes (`core/file_detection.py`), not
the extension.

**The LSB engines are general, not one hardcoded method.** Both the image
(`image/lsb.py`) and audio (`audio/pcm_lsb.py`) engines expose channel
selection/order, bit positions, traversal order, channel layout
(interleave/sequential), and output bit order. A CTF payload hidden with any of
these conventions can be recovered by setting parameters — or found
automatically by Smart Scan's bounded sweep.

**Lossy audio is handled honestly.** `audio/loader.py` only exposes integer PCM
samples for genuinely lossless sources (WAV/FLAC/AIFF). For MP3/OGG the sample
LSBs are decoder output, not hidden bits, so `pcm_lsb` raises `NotLosslessPCM`
rather than returning noise dressed up as a result.

**External tools never fake success.** `core/tools.py` runs every tool with an
argument list (no shell → no injection), a timeout, and an output cap, and
returns the exact argv plus stdout/stderr. Wrappers report failures truthfully;
a missing tool raises `ToolNotAvailable`, surfaced in the UI with an install
hint.

**Originals are immutable.** `core/storage.py` writes the uploaded bytes once.
Anything that mutates works on a copy in `data/work/`. Recovered payloads are
stored as first-class files with a `parent_id`, so the
`PNG → ZIP → text → flag` chain flows through the app without re-uploading.

**Long work is a background job.** `core/job_manager.py` runs frame extraction
and deep scans on a bounded thread pool with live progress and cancellation; the
frontend polls `/api/jobs/{id}`.

**Scoring is transparent.** `analysis/scoring.py` builds each score from
explained components (valid signature at offset 0, printable ratio, flag-like
token, entropy band…). The UI shows the reasons; a number is never presented as
proof on its own.

## Request flow example

`POST /api/smart-scan {file_id, depth}` →
`job_manager.submit` → `analysis/smart_scan.run_smart_scan`:

1. `storage.require(file_id)` and branch on `media_type`.
2. Run format-appropriate checks (trailing data, carve, a bounded set of LSB
   configs, bit-plane structure, external tools, metadata).
3. Score each candidate payload; store those above threshold via
   `storage.store_extracted`.
4. Rank and return findings; the UI polls the job and renders them, with saved
   payloads appearing in Results.

## Limits (all override-able via `STEGO_*` env vars)

| Setting | Default | Env var |
|--------|---------|---------|
| Max upload | 2 GiB | `STEGO_MAX_UPLOAD_BYTES` |
| Tool timeout | 120 s | `STEGO_TOOL_TIMEOUT` |
| Max image pixels | 80 MP | `STEGO_MAX_IMAGE_PIXELS` |
| Max LSB output | 64 MiB | `STEGO_MAX_LSB_OUTPUT` |
| Max audio length | 3600 s | `STEGO_MAX_AUDIO_SECONDS` |
| Max frames | 2000 | `STEGO_MAX_FRAMES` |
| Data directory | `backend/data` | `STEGO_DATA_DIR` |
