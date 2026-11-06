# Usage — worked examples

Open **http://127.0.0.1:5173** after `./scripts/start.sh`.

The core workflow is always: **UPLOAD → ANALYSE → INVESTIGATE → EXTRACT.**
Drag a file onto the Dashboard (or any page's file bar) to begin. The active
file is shared across every module.

## 1. Fast triage — Smart Scan

1. Upload a file. The Dashboard shows the detected format and suggested modules.
2. Pick **Quick / Standard / Deep** and click **Run Smart Scan**.
3. Findings are ranked with explained scores. Any recovered payload is saved and
   appears in **Results** for re-analysis.

Deep scan tests more bit-plane/traversal combinations and slower tools, within
hard caps — it never brute-forces every combination.

## 2. Image LSB by hand

`Image → LSB`. Choose channels (R/G/B/A), bit planes (0 = LSB), traversal
(row/column), channel layout (interleave/sequential), bit order (MSB/LSB first),
and plane order. Click **Extract** to see text decodings, flag-like tokens and a
hex preview. **Save payload** stores the raw bytes as a recovered file.

Tip: if a payload is in one channel only, set that single channel + *sequential*.

## 3. The classic `PNG → ZIP → flag` chain

1. Upload the PNG. `Image → Format` flags **trailing data after IEND**.
2. Go to **Results**, select the PNG, open the **extraction** tab, click
   **Carve embedded files** → the appended ZIP is recovered.
3. Select the carved ZIP; its **extraction** tab lists entries. Click **extract**
   on the inner file.
4. Open the extracted file's **text** tab — the flag is there.

Smart Scan does all of this in one click, but the manual path shows each step.

## 4. Audio: spectrogram hidden text

`Audio → Spectrogram`. Increase **FFT size** (e.g. 2048–4096) and **overlap**,
switch **scale** to linear or log, and raise the **dynamic range** to reveal
faint structure. Crop the frequency range to zoom into a band. Export the image
with **Export PNG**.

To analyse only part of the clip: on **Waveform**, drag-select a region (or type
start/end seconds). Every audio tool then operates on that range, and **Export
selected segment** writes it to a WAV you can re-open.

## 5. Audio: PCM sample LSB

`Audio → PCM LSB` (lossless sources only). Pick channel(s), bit position(s),
layout and bit order, then **Extract**. Detected file signatures inside the
payload are shown; **Save** stores it for carving/recursive extraction.

For lossy MP3/OGG the tool refuses and explains why — decoded sample LSBs are not
the hidden bits.

## 6. Audio: DTMF / Morse

`Audio → Decoders`. **DTMF** recovers touch-tone digit sequences (Goertzel);
**Morse** decodes a keyed CW tone to text; **SSTV** detects the VIS header and
names the mode (full image decode is intentionally out of scope — use QSSTV on
the exported segment).

## 7. Video frames and audio

`Video`:
- **Extract frames** by every-N / interval / scene change (runs as a job).
- Click a frame to preview it, then **Send to Image module** to run LSB/bitplane
  analysis on it.
- **Frame diff series** flags frames that change unusually (z-score outliers).
- **Extract audio track** drops a lossless WAV straight into the Audio workspace.

## 8. Results workspace

Every recovered payload lands here with source, method, parameters, size,
SHA-256 and a preview (text / hex / image / audio). From here you can:

- **Download** it,
- **Re-analyse** it in the matching module,
- **Carve** embedded files or run **Recursive extract**,
- list/extract **ZIP** entries.

## External tools

The Dashboard lists which of `zsteg`, `steghide`, `stegseek`, `outguess`,
`exiftool`, `binwalk`, `ffmpeg`, `tesseract` are installed. In `Image → Tools`
you can run each on the active file; the exact command and its stdout/stderr are
shown, and a missing tool reports how to install it rather than failing silently.
