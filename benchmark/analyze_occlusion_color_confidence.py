#!/usr/bin/env python3
"""Compare COLOR4 posterior confidence and absolute model distance under occlusion."""

from __future__ import annotations

import os
from dataclasses import asdict

import numpy as np

os.environ.setdefault("ORBIQO_RADIALCODE_ROOT", "/home/ubuntu/radialcode")

from run_normalized_comparison import PAYLOAD, PROFILES, OrbiqoAdapter  # noqa: E402
from radialcode.color import fit_color_model  # noqa: E402
from radialcode.constants import Alphabet, EccLevel, PayloadType  # noqa: E402
from radialcode.decoder import (  # noqa: E402
    _color_visibility_confidence,
    _large_neutral_black_components,
    _load_rgb,
    _sample_cell,
    _sample_cells,
)
from radialcode.encoder import encode  # noqa: E402
from radialcode.simulation import Degradation, degrade  # noqa: E402
from radialcode.vision import _detect_outer_guard_bgr, _frontal_rectification, _load_bgr  # noqa: E402


def summarize(values: np.ndarray) -> dict[str, float]:
    return {key: float(np.quantile(values, quantile)) for key, quantile in (("p05", 0.05), ("p50", 0.50), ("p95", 0.95), ("max", 1.0))}


def main() -> None:
    adapter = OrbiqoAdapter()
    generated = adapter.generate_normalized(PAYLOAD)
    symbol = encode(PAYLOAD, payload_type=PayloadType.BINARY, geometry="auto", diameter_mm=30.0, alphabet=Alphabet.COLOR4, ecc_level=EccLevel.BALANCED, compression="none")
    geometry = symbol.geometry
    profile = PROFILES["occlusion_0_06"]
    cases = [("clean", generated.image)] + [
        (f"occlusion_{trial + 101}", degrade(generated.image, Degradation(**{**asdict(profile), "seed": trial + 101})))
        for trial in range(4)
    ]
    for label, image in cases:
        bgr = _load_bgr(image)
        rectified = _frontal_rectification(bgr, _detect_outer_guard_bgr(bgr), 1024)
        array = _load_rgb(rectified.image)
        grouped: dict[int, list[tuple[float, float, float]]] = {}
        for address, state in geometry.calibration_addresses(Alphabet.COLOR4).items():
            grouped.setdefault(state, []).append(_sample_cell(array, geometry.cell(address)))
        model = fit_color_model(grouped, regularization=36.0)
        addresses = geometry.payload_addresses(Alphabet.COLOR4)
        samples = _sample_cells(array, [geometry.cell(address) for address in addresses])
        classified = model.classify_many(samples)
        posterior = np.asarray([item.confidence for item in classified], dtype=np.float64)
        nearest = np.asarray([min(item.mahalanobis_distances) for item in classified], dtype=np.float64)
        black_components = _large_neutral_black_components(samples, addresses, geometry)
        effective = np.asarray(
            [
                min(item.confidence, _color_visibility_confidence(sample), 0.0 if index in black_components else 1.0)
                for index, (item, sample) in enumerate(zip(classified, samples, strict=True))
            ],
            dtype=np.float64,
        )
        print({
            "case": label,
            "posterior": summarize(posterior),
            "nearest_distance": summarize(nearest),
            "posterior_below_0_55": int(np.sum(posterior < 0.55)),
            "nearest_above_12": int(np.sum(nearest > 12.0)),
            "nearest_above_25": int(np.sum(nearest > 25.0)),
            "white_erasures": int(sum(_color_visibility_confidence(sample) == 0.0 for sample in samples)),
            "black_component_erasures": len(black_components),
            "effective_erasures": int(np.sum(effective < 0.55)),
        })


if __name__ == "__main__":
    main()
