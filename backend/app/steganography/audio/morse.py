"""Morse code decoder from an audio tone.

Approach: compute the amplitude envelope, threshold it into on/off segments,
cluster the on-durations into dots vs dashes and the off-durations into
intra-character / inter-character / word gaps, then translate. Works for a
single keyed tone (CW) which is the usual CTF case.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .loader import load_audio, slice_frames

_MORSE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F",
    "--.": "G", "....": "H", "..": "I", ".---": "J", "-.-": "K", ".-..": "L",
    "--": "M", "-.": "N", "---": "O", ".--.": "P", "--.-": "Q", ".-.": "R",
    "...": "S", "-": "T", "..-": "U", "...-": "V", ".--": "W", "-..-": "X",
    "-.--": "Y", "--..": "Z",
    "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4",
    ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9",
    ".-.-.-": ".", "--..--": ",", "..--..": "?", "-..-.": "/", "-.--.": "(",
    "-.--.-": ")", ".-...": "&", "---...": ":", "-.-.-.": ";", "-...-": "=",
    ".-.-.": "+", "-....-": "-", "..--.-": "_", ".-..-.": '"', "...-..-": "$",
    ".--.-.": "@",
}


def decode(path: str | Path, *, channel: int = 0, win_ms: float = 5.0,
           start: Optional[float] = None, end: Optional[float] = None) -> dict:
    a = load_audio(path)
    ch = min(channel, a.channels - 1)
    s, e = slice_frames(a.sample_rate, start, end, a.n_frames)
    sig = a.float_samples[s:e, ch]
    sr = a.sample_rate
    if sig.size < sr // 10:
        raise ValueError("Segment too short for Morse analysis")

    win = max(1, int(sr * win_ms / 1000))
    nwin = sig.size // win
    env = np.sqrt(np.mean(sig[:nwin * win].reshape(nwin, win) ** 2, axis=1))
    thr = (env.max() * 0.3) if env.size else 0.0
    on = env > thr

    # run-length encode on/off in units of win
    runs = []
    cur = on[0] if on.size else False
    length = 0
    for v in on:
        if v == cur:
            length += 1
        else:
            runs.append((cur, length))
            cur = v
            length = 1
    runs.append((cur, length))

    on_durs = [l for state, l in runs if state]
    off_durs = [l for state, l in runs if not state]
    if not on_durs:
        return {"method": "morse", "text": "", "morse": "", "note": "No keyed tone detected"}

    # cluster on durations: dot vs dash using median split
    unit = np.median(on_durs)
    off_unit = np.median(off_durs) if off_durs else unit

    morse_tokens = []
    for state, length in runs:
        if state:
            morse_tokens.append("." if length < 2 * unit else "-")
        else:
            if length < 2 * max(off_unit, unit):
                morse_tokens.append("")          # intra-character gap
            elif length < 5 * max(off_unit, unit):
                morse_tokens.append(" ")         # letter gap
            else:
                morse_tokens.append(" / ")       # word gap

    morse_str = "".join(morse_tokens).strip()
    text = _translate(morse_str)
    return {
        "method": "morse_envelope",
        "parameters": {"channel": ch, "unit_windows": float(unit)},
        "morse": morse_str,
        "text": text,
    }


def _translate(morse: str) -> str:
    words = morse.split(" / ")
    out_words = []
    for w in words:
        letters = [l for l in w.split(" ") if l]
        out_words.append("".join(_MORSE.get(l, "?") for l in letters))
    return " ".join(out_words)
