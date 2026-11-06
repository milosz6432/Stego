"""Image LSB engine: exact payload recovery and parameter sensitivity."""
import numpy as np
import pytest
from PIL import Image

from app.steganography.image import lsb
from tests.conftest import embed_lsb_png


def test_exact_recovery_single_channel(png_lsb):
    params = lsb.LSBParams(channels=["R"], bit_planes=[0], channel_mode="sequential",
                           bit_order="msb", traversal="row")
    raw = lsb.extract_raw(png_lsb, params)
    assert raw.startswith(b"FLAG{image_lsb_recovered}")


def test_interesting_finds_flag(png_lsb):
    params = lsb.LSBParams(channels=["R"], bit_planes=[0], channel_mode="sequential")
    out = lsb.extract(png_lsb, params)
    assert "FLAG{image_lsb_recovered}" in out["interesting"]["flags"]


def test_wrong_bit_order_does_not_recover(png_lsb):
    params = lsb.LSBParams(channels=["R"], bit_planes=[0], channel_mode="sequential", bit_order="lsb")
    raw = lsb.extract_raw(png_lsb, params)
    assert not raw.startswith(b"FLAG{image_lsb_recovered}")


def test_wrong_channel_does_not_recover(png_lsb):
    params = lsb.LSBParams(channels=["G"], bit_planes=[0], channel_mode="sequential")
    raw = lsb.extract_raw(png_lsb, params)
    assert not raw.startswith(b"FLAG{image_lsb_recovered}")


def test_blue_channel_roundtrip(tmp_path):
    p = tmp_path / "blue.png"
    embed_lsb_png(p, b"FLAG{blue_lsb}\x00", channel="B")
    params = lsb.LSBParams(channels=["B"], bit_planes=[0], channel_mode="sequential")
    assert lsb.extract_raw(p, params).startswith(b"FLAG{blue_lsb}")


def test_column_traversal_differs(tmp_path):
    p = tmp_path / "x.png"
    embed_lsb_png(p, b"FLAG{row_major_only}\x00")
    row = lsb.extract_raw(p, lsb.LSBParams(channels=["R"], channel_mode="sequential", traversal="row"))
    col = lsb.extract_raw(p, lsb.LSBParams(channels=["R"], channel_mode="sequential", traversal="column"))
    assert row.startswith(b"FLAG{row_major_only}")
    assert row != col


def test_params_normalise_dedups_planes():
    params = lsb.LSBParams(bit_planes=[0, 0, 9, 3, -1]).normalise()
    assert params.bit_planes == [0, 3]
