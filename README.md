# STEGO LAB — Advanced CTF Steganography Workbench

A local, web-based steganography analysis tool built for CTF challenges. It
finds, visualises and **extracts** hidden data from **images, audio and video**
using real algorithms — not placeholders. Every analysis runs locally; nothing
is uploaded to any third-party service.

> Focus: practical, technically-correct extraction. Fewer fully-working methods
> beat dozens of fake ones.

---

## What it does

| Area | Capabilities |
|------|-------------|
| **Image** | Configurable LSB engine (channels, bit-planes 0–7, row/column traversal, MSB/LSB bit order, interleave/sequential, plane order), interactive bit-plane viewer with structure scoring, channel separation / histograms / LSB χ² / transforms / differences, PNG·JPEG·BMP·GIF·TIFF·WebP structural parsers (chunks, markers, trailing-data detection), and one-click `zsteg` / `steghide` / `stegseek` / `outguess` / `exiftool` / `binwalk` / Tesseract OCR. |
| **Audio** | Dedicated workspace: player, waveform + RMS/peak/silence, **fully-configurable spectrogram** (FFT size, hop/overlap, window, linear/log/mel, dB range, colormaps, freq cropping), FFT with peak & harmonic detection, **PCM sample-LSB engine** (bit positions, channels, interleave, bit order), phase-coding / echo-hiding / stereo / zero-crossing / repetition heuristics, and **DTMF / Morse** decoders + SSTV VIS detection. Time-range selection drives every tool, and segments export to WAV. |
| **Video** | ffprobe container/stream info, frame extraction (every-N / interval / scene-change / contact sheet) as background jobs, frame-difference anomaly detection, send any frame to the Image module, and lossless audio extraction straight into the Audio workspace. |
| **Extraction** | Signature scanning & carving (ZIP/PNG/JPEG/PDF/… with footers), appended-payload recovery, ZIP listing/extraction, recursive analysis — e.g. `PNG → appended ZIP → text → flag` without re-uploading. |
| **Smart Scan** | Format-aware orchestration (quick / standard / deep) that runs the techniques that apply, tests a **bounded** set of extraction configs, inspects the results, and ranks findings with **transparent, explained scores**. |

Recovered payloads are collected in the **Results** workspace with SHA-256,
hex/text/image/audio previews, download, and one-click re-analysis in the right
module.

---

## Requirements

- **Python 3.12+**
- **Node.js 18+** (for the frontend)
- Optional external tools (the app detects them and degrades honestly when
  absent): `zsteg`, `steghide`, `stegseek`, `outguess`, `exiftool`, `binwalk`,
  `ffmpeg`/`ffprobe`, `tesseract`.

`ffmpeg`/`ffprobe` are **required for video** and for decoding compressed audio
(MP3/OGG). Everything else is optional.

---

## Quick start

```bash
# 1. Install backend + frontend dependencies (creates backend/.venv)
./scripts/setup.sh

# 2. (optional) Install the external CLI tools — Debian/Ubuntu
./scripts/install-tools.sh

# 3. Run both servers (backend :8000, frontend :5173)
./scripts/start.sh
```

Then open **http://127.0.0.1:5173**. Drag a file in, or click to browse.

### Manual start (if you prefer)

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev
```

API docs (interactive OpenAPI) are at **http://127.0.0.1:8000/docs**.

---

## Installing the optional tools manually

Debian/Ubuntu:

```bash
sudo apt-get install -y steghide stegseek outguess libimage-exiftool-perl \
                        binwalk tesseract-ocr ffmpeg ruby
sudo gem install zsteg
```

macOS (Homebrew):

```bash
brew install steghide outguess exiftool binwalk tesseract ffmpeg
gem install zsteg
# stegseek: see https://github.com/RickdeJager/stegseek/releases
```

The Dashboard shows which tools are detected; features needing a missing tool
say so instead of faking a result.

---

## Running the tests

Backend (71 tests — includes exact-payload round-trips for image LSB, PCM LSB,
stereo channels, format parsers, carving, Smart Scan, API, and edge cases;
external-tool tests skip cleanly when a tool is absent):

```bash
cd backend
source .venv/bin/activate
pytest
```

Frontend unit tests:

```bash
cd frontend
npm test
```

---

## How the pieces fit together

```
UPLOAD ─▶ detect format (magic bytes) ─▶ ANALYSE (per-module) ─▶ INVESTIGATE ─▶ EXTRACT
                                             │                                     │
                                        Smart Scan ──────────────▶ ranked findings ┘
```

- The original upload is stored **immutably**; analysis works on copies.
- Long operations run as **background jobs** with live progress.
- Recovered payloads become first-class files you can re-feed into any module.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full module map and
[`docs/USAGE.md`](docs/USAGE.md) for worked examples.

---

## Safety & engineering notes

- All processing is **local**. No file leaves your machine.
- External tools are invoked with **argument lists (never a shell)**, with
  timeouts and output caps — no command injection.
- Recovered payloads are **never executed**.
- Resource limits guard image pixels, audio length, frame counts and output size.
- Each steganographic method lives in its own backend module; the frontend
  implements **none** of the core algorithms — it only calls the API.

## License

Provided for authorised security testing, CTF competitions and educational use.
