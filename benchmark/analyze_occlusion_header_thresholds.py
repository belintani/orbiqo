#!/usr/bin/env python3
"""Sweep fixed black/white thresholds on retified header rings under 6% occlusion."""

from __future__ import annotations

import os
from dataclasses import asdict

os.environ.setdefault("ORBIQO_RADIALCODE_ROOT", "/home/ubuntu/radialcode")

from run_normalized_comparison import PAYLOAD, PROFILES, OrbiqoAdapter  # noqa: E402
from radialcode.bootstrap import header_physical_bits  # noqa: E402
from radialcode.constants import Alphabet, EccLevel, HEADER_PHYSICAL_SLOTS, HEADER_RINGS, PayloadType  # noqa: E402
from radialcode.decoder import _load_rgb, _luma, _sample_patch  # noqa: E402
from radialcode.encoder import encode  # noqa: E402
from radialcode.simulation import Degradation, degrade  # noqa: E402
from radialcode.vision import _detect_outer_guard_bgr, _frontal_rectification, _load_bgr  # noqa: E402


def hamming(left, right):  # type: ignore[no-untyped-def]
    return sum(first != second for first, second in zip(left, right, strict=True))


def main() -> None:
    adapter = OrbiqoAdapter()
    generated = adapter.generate_normalized(PAYLOAD)
    symbol = encode(PAYLOAD, payload_type=PayloadType.BINARY, geometry="auto", diameter_mm=30.0, alphabet=Alphabet.COLOR4, ecc_level=EccLevel.BALANCED, compression="none")
    expected = tuple(header_physical_bits(symbol.header, index) for index in range(3))
    profile = PROFILES["occlusion_0_06"]
    cases = [("clean", generated.image)] + [
        (f"occ_{trial + 101}", degrade(generated.image, Degradation(**{**asdict(profile), "seed": trial + 101})))
        for trial in range(4)
    ]
    thresholds = tuple(range(40, 221, 5))
    for label, image in cases:
        bgr = _load_bgr(image)
        rectified = _frontal_rectification(bgr, _detect_outer_guard_bgr(bgr), 1024)
        array = _load_rgb(rectified.image)
        ring_lumas = []
        for r_inner, r_outer in HEADER_RINGS:
            radius = (r_inner + r_outer) / 2.0
            ring_lumas.append([
                _luma(_sample_patch(array, normalized_radius=radius, theta=(slot + 0.5) * 2.0 * 3.141592653589793 / HEADER_PHYSICAL_SLOTS, patch_radius=0))
                for slot in range(HEADER_PHYSICAL_SLOTS)
            ])
        result = []
        for index, values in enumerate(ring_lumas):
            errors = [(threshold, hamming(expected[index], tuple(1 if value < threshold else 0 for value in values))) for threshold in thresholds]
            result.append({"ring": index, "at_128": dict(errors)[130], "best": min(errors, key=lambda item: item[1])})
        print({"case": label, "rings": result})


if __name__ == "__main__":
    main()
