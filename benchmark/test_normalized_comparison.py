from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
RADIAL_ROOT = Path(os.environ.get("ORBIQO_RADIALCODE_ROOT", ROOT.parent / "radialcode")).resolve()
sys.path.insert(0, str(RADIAL_ROOT / "src"))

from radialcode.simulation import Degradation, degrade

from run_normalized_comparison import (
    CANVAS_SIZE,
    MIN_FEATURE_PITCH_PX,
    OCCUPIED_SIZE,
    PAYLOAD,
    PROFILES,
    build_adapters,
)


def test_normalization_constants_are_intentionally_fixed() -> None:
    assert CANVAS_SIZE == 1024
    assert OCCUPIED_SIZE == 900
    assert MIN_FEATURE_PITCH_PX == 7.0
    assert len(PAYLOAD) == 64


@pytest.mark.parametrize("adapter_index", [0, 1, 2, 3])
def test_each_adapter_round_trips_the_same_normalized_payload(adapter_index: int) -> None:
    adapters, status = build_adapters()
    if adapter_index >= len(adapters):
        pytest.skip(f"optional adapter unavailable: {status}")
    adapter = adapters[adapter_index]
    generated = adapter.generate_normalized(PAYLOAD)
    assert generated.image.size == (CANVAS_SIZE, CANVAS_SIZE)
    assert generated.nominal_pitch_px > MIN_FEATURE_PITCH_PX
    assert adapter.decode(generated.image) == PAYLOAD


def test_degradation_profiles_use_fixed_names_and_reproducible_seeds() -> None:
    assert list(PROFILES) == [
        "clean",
        "blur_1_5",
        "blur_3_0",
        "noise_8",
        "jpeg_40",
        "downsample_0_35",
        "occlusion_0_06",
        "combined",
    ]
    image = Image.new("RGB", (128, 128), (90, 130, 170))
    profile = PROFILES["combined"]
    first = degrade(image, Degradation(**{**asdict(profile), "seed": 101}))
    second = degrade(image, Degradation(**{**asdict(profile), "seed": 101}))
    different = degrade(image, Degradation(**{**asdict(profile), "seed": 102}))
    assert np.array_equal(np.asarray(first), np.asarray(second))
    assert not np.array_equal(np.asarray(first), np.asarray(different))


def test_adapter_profiles_and_ecc_are_explicit() -> None:
    adapters, status = build_adapters()
    profiles = {adapter.name: adapter.generate_normalized(PAYLOAD) for adapter in adapters}
    assert "balanced" in profiles["orbiqo"].profile
    assert "RS(255,191)" in profiles["orbiqo"].reported_ecc
    assert "requested ECC Q" in profiles["qr"].profile
    assert profiles["qr"].reported_ecc == "Q"
    assert "requested ECC 25" in profiles["aztec"].profile
    assert profiles["aztec"].reported_ecc.endswith("%")
    if status["included"]:
        assert "level 3" in profiles["jab"].profile
        assert profiles["jab"].reported_ecc == "level 3 (CLI: 6%)"
