#!/usr/bin/env python3
"""Inspect the canonical format-5 outer BCH copy on the normalized benchmark raster."""

from __future__ import annotations

from radialcode.bootstrap import header_codeword_from_physical, header_physical_bits
from radialcode.constants import OUTER_HEADER_RING
from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.decoder import _luma, _sample_outer_header_ring, _sample_patch
from radialcode.encoder import encode
from radialcode.header import RadialHeader
from radialcode.renderer import render_png_fast
from radialcode.vision import _detect_outer_guard_bgr, _frontal_rectification
from PIL import Image
from io import BytesIO

from run_normalized_comparison import ORBIQO_NORMALIZED_DPI, PAYLOAD, OrbiqoAdapter


def sample(array, radius: float) -> tuple[int, ...]:
    from math import pi

    return tuple(
        1 if _luma(_sample_patch(array, normalized_radius=radius, theta=(slot + 0.5) * 2.0 * pi / 64, patch_radius=0)) < 150 else 0
        for slot in range(64)
    )


def luminances(array, radius: float) -> list[float]:
    from math import pi

    return [
        _luma(_sample_patch(array, normalized_radius=radius, theta=(slot + 0.5) * 2.0 * pi / 64, patch_radius=0))
        for slot in range(64)
    ]


def main() -> None:
    adapter = OrbiqoAdapter()
    generated = adapter.generate_normalized(PAYLOAD)
    array = __import__("numpy").asarray(generated.image, dtype=float)
    symbol = encode(PAYLOAD, payload_type=PayloadType.BINARY, geometry="auto", diameter_mm=30.0, alphabet=Alphabet.COLOR4, ecc_level=EccLevel.BALANCED, compression="none")
    direct = Image.open(BytesIO(render_png_fast(symbol, dpi=ORBIQO_NORMALIZED_DPI, supersample=2))).convert("RGB")
    direct_array = __import__("numpy").asarray(direct, dtype=float)
    import cv2
    benchmark_bgr = cv2.cvtColor(__import__("numpy").asarray(generated.image, dtype=__import__("numpy").uint8), cv2.COLOR_RGB2BGR)
    rectified = _frontal_rectification(benchmark_bgr, _detect_outer_guard_bgr(benchmark_bgr), 1024)
    rectified_array = __import__("numpy").asarray(rectified.image, dtype=float)
    print({"adapter_size": generated.image.size, "direct_size": direct.size, "format": symbol.header.format_version})
    expected = header_physical_bits(symbol.header, 3)
    expected_radius = (OUTER_HEADER_RING[0] + OUTER_HEADER_RING[1]) / 2.0
    best = None
    for step in range(int((expected_radius - 0.03) * 1000), int((expected_radius + 0.03) * 1000) + 1):
        radius = step / 1000.0
        values = luminances(rectified_array, radius)
        for threshold in range(40, 221, 2):
            bits = tuple(1 if value < threshold else 0 for value in values)
            errors = sum(left != right for left, right in zip(bits, expected, strict=True))
            candidate = (errors, radius, threshold)
            if best is None or candidate < best:
                best = candidate
    print({"rectified_best_outer_alignment": best})
    for radius in (expected_radius - 0.004, expected_radius, expected_radius + 0.004):
        values = luminances(array, radius)
        bits = tuple(1 if value < 150 else 0 for value in values)
        errors = sum(left != right for left, right in zip(bits, expected, strict=True))
        try:
            header, corrected = RadialHeader.decode_codeword(header_codeword_from_physical(bits, 3))
            result = f"ok:{header.format_version}/{corrected}"
        except Exception as exc:  # diagnostic only
            result = type(exc).__name__
        print({"radius": radius, "errors": errors, "decode": result, "luma": (min(values), max(values)), "dark_slots": sum(bits)})
        print({"radius": radius, "direct_luma": (min(luminances(direct_array, radius)), max(luminances(direct_array, radius)))})
        rectified_values = luminances(rectified_array, radius)
        try:
            rectified_bits = _sample_outer_header_ring(rectified_array, radius)
            rectified_errors = sum(left != right for left, right in zip(rectified_bits, expected, strict=True))
            rectified_header, rectified_corrected = RadialHeader.decode_codeword(header_codeword_from_physical(rectified_bits, 3))
            rectified_decode = f"ok:{rectified_header.format_version}/{rectified_corrected}"
        except Exception as exc:
            rectified_errors = None
            rectified_decode = type(exc).__name__
        print({"radius": radius, "rectified_luma": (min(rectified_values), max(rectified_values)), "rectified_errors": rectified_errors, "rectified_decode": rectified_decode})


if __name__ == "__main__":
    main()
