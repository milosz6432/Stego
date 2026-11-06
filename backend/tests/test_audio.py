"""Audio engines: PCM-LSB exact recovery, lossy refusal, DSP, decoders."""
import numpy as np
import pytest

from app.steganography.audio import (
    advanced, dtmf, fft, morse, pcm_lsb, segment, spectrogram, waveform,
)
from app.steganography.audio.loader import load_audio


def test_pcm_lsb_exact_recovery(wav_pcm):
    params = pcm_lsb.PCMParams(channels=[0], bit_planes=[0], channel_mode="interleave", bit_order="msb")
    raw = pcm_lsb.extract_raw(wav_pcm, params)
    assert raw.startswith(b"FLAG{pcm_lsb_recovered}")


def test_pcm_lsb_finds_flag(wav_pcm):
    out = pcm_lsb.extract(wav_pcm, pcm_lsb.PCMParams(channels=[0], bit_planes=[0]))
    assert "FLAG{pcm_lsb_recovered}" in out["interesting"]["flags"]
    assert out["audio"]["sample_width_bits"] == 16


def test_stereo_independent_channels(wav_stereo):
    left = pcm_lsb.extract_raw(wav_stereo, pcm_lsb.PCMParams(channels=[0], channel_mode="sequential"))
    right = pcm_lsb.extract_raw(wav_stereo, pcm_lsb.PCMParams(channels=[1], channel_mode="sequential"))
    assert left.startswith(b"LEFT{channel_zero}")
    assert right.startswith(b"RIGHT{channel_one}")


def test_pcm_lsb_refuses_lossy(tmp_path):
    import soundfile as sf
    # Build an OGG (lossy) file; decoded LSBs are not meaningful.
    p = tmp_path / "x.ogg"
    sig = (np.sin(2 * np.pi * 300 * np.arange(44100) / 44100)).astype(np.float32)
    try:
        sf.write(p, sig, 44100, format="OGG", subtype="VORBIS")
    except Exception:
        pytest.skip("OGG/Vorbis encoding not available")
    with pytest.raises(pcm_lsb.NotLosslessPCM):
        pcm_lsb.extract(p, pcm_lsb.PCMParams(channels=[0]))


def test_waveform_shape(wav_pcm):
    w = waveform.waveform(wav_pcm, buckets=500)
    assert len(w["peaks"][0]) == 500
    assert w["sample_rate"] == 44100


def test_statistics(wav_stereo):
    s = waveform.statistics(wav_stereo)
    assert len(s["per_channel"]) == 2


def test_spectrogram_render(wav_pcm):
    png, meta = spectrogram.spectrogram_image(wav_pcm, cmap="magma", n_fft=1024, scale="log")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert meta["freq_bins"] > 0 and meta["time_frames"] > 0


def test_spectrogram_mel(wav_pcm):
    png, meta = spectrogram.spectrogram_image(wav_pcm, scale="mel", n_mels=64)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_fft_peak_detection(tmp_path):
    import soundfile as sf
    sr = 22050
    sig = np.sin(2 * np.pi * 1000 * np.arange(sr) / sr).astype(np.float32)
    p = tmp_path / "tone.wav"
    sf.write(p, sig, sr, subtype="PCM_16")
    out = fft.spectrum(p, channel=0)
    top = out["peaks"][0]["frequency"]
    assert abs(top - 1000) < 20


def test_dtmf_decode(dtmf_wav):
    out = dtmf.decode(dtmf_wav)
    assert out["sequence"] == "19073"


def test_morse_decode(morse_wav):
    out = morse.decode(morse_wav)
    assert out["text"] == "SOS"
    assert out["morse"].replace(" ", "") == "...---..."


def test_segment_export_is_wav(wav_pcm):
    data, meta = segment.export_segment(wav_pcm, 0.0, 0.1)
    assert data[:4] == b"RIFF"
    assert meta["sample_rate"] == 44100


def test_stereo_analysis(wav_stereo):
    out = advanced.stereo_analysis(wav_stereo)
    assert out["channels"] == 2
    assert "correlation" in out


def test_echo_analysis_runs(wav_pcm):
    out = advanced.echo_analysis(wav_pcm)
    assert out["method"] == "echo_hiding"
    assert "cepstrum" in out
