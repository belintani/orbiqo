#!/usr/bin/env python3
"""Prototype a fourth BCH copy in the unused outer band for 6% occlusion analysis."""

from __future__ import annotations

import os
from dataclasses import asdict
from io import BytesIO
from math import cos, pi, sin

from PIL import Image, ImageDraw

os.environ.setdefault("ORBIQO_RADIALCODE_ROOT", "/home/ubuntu/radialcode")

from run_normalized_comparison import PAYLOAD, PROFILES, normalize_fixed  # noqa: E402
from radialcode.bootstrap import header_codeword_from_physical, header_physical_bits  # noqa: E402
from radialcode.constants import Alphabet, EccLevel, HEADER_PHYSICAL_SLOTS, PayloadType, QUIET_ZONE_OUTER  # noqa: E402
import radialcode.decoder as decoder_module  # noqa: E402
from radialcode.decoder import DecodeError, _adaptive_binary_threshold, _load_rgb, _luma, _sample_patch  # noqa: E402
from radialcode.encoder import encode  # noqa: E402
from radialcode.header import RadialHeader  # noqa: E402
from radialcode.renderer import RenderOptions, render_png_fast  # noqa: E402
from radialcode.simulation import Degradation, degrade  # noqa: E402
from radialcode.vision import _detect_outer_guard_bgr, _frontal_rectification, _load_bgr, decode_image  # noqa: E402


OUTER_HEADER_INNER = 0.912
OUTER_HEADER_OUTER = 0.928
OUTER_HEADER_SAMPLE_RADIUS = 0.934


def draw_outer_header(image: Image.Image, header: RadialHeader) -> Image.Image:
    output = image.convert("RGB").copy()
    draw = ImageDraw.Draw(output)
    center = output.width / 2.0
    radius = output.width / (2.0 * QUIET_ZONE_OUTER)
    inner = OUTER_HEADER_INNER * radius
    outer = OUTER_HEADER_OUTER * radius
    bits = header_physical_bits(header, 0)
    for slot, bit in enumerate(bits):
        start = (slot + 0.11) * 2.0 * pi / HEADER_PHYSICAL_SLOTS
        end = (slot + 0.89) * 2.0 * pi / HEADER_PHYSICAL_SLOTS
        points = [
            (center + inner * sin(start), center - inner * cos(start)),
            (center + outer * sin(start), center - outer * cos(start)),
            (center + outer * sin(end), center - outer * cos(end)),
            (center + inner * sin(end), center - inner * cos(end)),
        ]
        draw.polygon(points, fill=(17, 17, 17) if bit else (255, 255, 255))
    return output


def decode_outer_header(array) -> tuple[RadialHeader, tuple[int, ...]]:  # type: ignore[no-untyped-def]
    radius = OUTER_HEADER_SAMPLE_RADIUS
    luminances = [
        _luma(_sample_patch(array, normalized_radius=radius, theta=(slot + 0.5) * 2.0 * pi / HEADER_PHYSICAL_SLOTS, patch_radius=0))
        for slot in range(HEADER_PHYSICAL_SLOTS)
    ]
    threshold = _adaptive_binary_threshold(luminances)
    bits = tuple(1 if value < threshold else 0 for value in luminances)
    header, corrected = RadialHeader.decode_codeword(header_codeword_from_physical(bits, 0))
    return header, (corrected,)


def main() -> None:
    original = decoder_module._decode_header
    payloads = {
        "benchmark": PAYLOAD,
        "ramp": bytes(range(len(PAYLOAD))),
        "affine": bytes((index * 73 + 19) % 256 for index in range(len(PAYLOAD))),
    }
    for ecc in (EccLevel.BALANCED, EccLevel.ROBUST, EccLevel.EXTREME):
      for payload_name, payload in payloads.items():
        symbol = encode(payload, payload_type=PayloadType.BINARY, geometry="auto", diameter_mm=30.0, alphabet=Alphabet.COLOR4, ecc_level=ecc, compression="none")
        native = Image.open(BytesIO(render_png_fast(symbol, dpi=725, options=RenderOptions(center_text="OQ"), supersample=2))).convert("RGB")
        image = normalize_fixed(draw_outer_header(native, symbol.header))

        def with_outer_fallback(array):  # type: ignore[no-untyped-def]
            try:
                return original(array)
            except DecodeError:
                return decode_outer_header(array)

        decoder_module._decode_header = with_outer_fallback
        clean_bgr = _load_bgr(image)
        clean_rectified = _frontal_rectification(clean_bgr, _detect_outer_guard_bgr(clean_bgr), 1024)
        clean_array = _load_rgb(clean_rectified.image)
        expected_outer = header_physical_bits(symbol.header, 0)
        best = None
        for step in range(800, 961, 2):
            radius = step / 1000.0
            values = [
                _luma(_sample_patch(clean_array, normalized_radius=radius, theta=(slot + 0.5) * 2.0 * pi / HEADER_PHYSICAL_SLOTS, patch_radius=0))
                for slot in range(HEADER_PHYSICAL_SLOTS)
            ]
            for threshold in range(40, 221, 5):
                bits = tuple(1 if value < threshold else 0 for value in values)
                errors = sum(left != right for left, right in zip(bits, expected_outer, strict=True))
                candidate = (errors, radius, threshold)
                if best is None or candidate < best:
                    best = candidate
        print({"ecc": ecc.name.lower(), "geometry": symbol.geometry.version.name, "clean_outer_alignment": best})
        profile = PROFILES["occlusion_0_06"]
        results = []
        cases = [("clean", image)] + [
            (f"occ_{trial + 101}", degrade(image, Degradation(**{**asdict(profile), "seed": trial + 101})))
            for trial in range(4)
        ]
        for label, degraded in cases:
            try:
                bgr = _load_bgr(degraded)
                rectified = _frontal_rectification(bgr, _detect_outer_guard_bgr(bgr), 1024)
                outer_header, outer_corrections = decode_outer_header(_load_rgb(rectified.image))
                header_status = f"ok:{outer_header.geometry_version}/{outer_corrections[0]}"
            except Exception as error:
                header_status = type(error).__name__
            try:
                decoded = decode_image(degraded).decoded
                results.append(decoded.payload == payload)
                payload_status = "ok" if results[-1] else "mismatch"
            except Exception as error:
                results.append(False)
                payload_status = type(error).__name__
            print({"ecc": ecc.name.lower(), "payload": payload_name, "case": label, "outer_header": header_status, "payload_status": payload_status})
        print({"prototype": "outer_header_copy", "ecc": ecc.name.lower(), "payload": payload_name, "successes": sum(results), "trials": 4, "results": results})
    decoder_module._decode_header = original


if __name__ == "__main__":
    main()
