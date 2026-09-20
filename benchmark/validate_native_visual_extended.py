#!/usr/bin/env python3
"""Expanded digital matrix for the native C++ decoder versus the Python oracle."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "server/python/vendor/radialcode/src"))
from validate_native_visual_matrix import (  # noqa: E402
    EXPECTED_PAYLOAD_B64,
    PAYLOAD,
    bridge_decode,
    encode_native,
    gaussian_noise,
    occlude,
    perspective,
    pixel_metrics,
    python_reference,
    recompress,
)

OUTPUT = ROOT / "benchmark/results/native_visual_extended.json"

@dataclass(frozen=True)
class Case:
    name: str
    image: bytes
    canonical: bool = False


def blur(image: bytes, radius: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    kernel = max(3, int(round(radius * 2)) * 2 + 1)
    filtered = cv2.GaussianBlur(source, (kernel, kernel), radius)
    ok, encoded = cv2.imencode(".png", filtered)
    assert ok
    return encoded.tobytes()


def downsample(image: bytes, factor: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = source.shape[:2]
    small = cv2.resize(source, (max(32, int(width * factor)), max(32, int(height * factor)),), interpolation=cv2.INTER_AREA)
    restored = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode(".png", restored)
    assert ok
    return encoded.tobytes()


def brightness(image: bytes, alpha: float, beta: int) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    adjusted = cv2.convertScaleAbs(source, alpha=alpha, beta=beta)
    ok, encoded = cv2.imencode(".png", adjusted)
    assert ok
    return encoded.tobytes()


def rotate(image: bytes, degrees: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = source.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), degrees, 1.0)
    rotated = cv2.warpAffine(source, matrix, (width, height), borderValue=(255, 255, 255))
    ok, encoded = cv2.imencode(".png", rotated)
    assert ok
    return encoded.tobytes()


def cases(image: bytes) -> list[Case]:
    return [
        Case("clean-vision", image),
        Case("perspective-mild", perspective(image, 0.25)),
        Case("perspective-medium", perspective(image, 0.60)),
        Case("perspective-severe", perspective(image, 1.00)),
        Case("noise-sigma-3", gaussian_noise(image, 3.0)),
        Case("noise-sigma-8", gaussian_noise(image, 8.0)),
        Case("blur-radius-1", blur(image, 1.0)),
        Case("blur-radius-2", blur(image, 2.0)),
        Case("jpeg-q95", recompress(image, "JPEG", 95)),
        Case("jpeg-q70", recompress(image, "JPEG", 70)),
        Case("webp-q90", recompress(image, "WEBP", 90)),
        Case("webp-q60", recompress(image, "WEBP", 60)),
        Case("downsample-0.75", downsample(image, 0.75)),
        Case("downsample-0.50", downsample(image, 0.50)),
        Case("brightness-dim", brightness(image, 0.82, 0)),
        Case("brightness-lift", brightness(image, 1.0, 22)),
        Case("rotation-minus-6", rotate(image, -6.0)),
        Case("rotation-plus-6", rotate(image, 6.0)),
        Case("occlusion-top-left", occlude(image, (0.27, 0.27))),
        Case("occlusion-top-right", occlude(image, (0.73, 0.27))),
        Case("occlusion-bottom-left", occlude(image, (0.27, 0.73))),
        Case("occlusion-bottom-right", occlude(image, (0.73, 0.73))),
    ]


def main() -> int:
    rows: list[dict[str, object]] = []
    pixels: list[dict[str, object]] = []
    for geometry, diameter in ((1, 30.0), (2, 40.0)):
        native_png = encode_native(geometry, diameter)
        reference_png = python_reference(geometry, diameter)
        pixels.append({"geometry": geometry, "diameter_mm": diameter, **pixel_metrics(native_png, reference_png)})
        for case in cases(native_png):
            native_ok, native_message, native_ms = bridge_decode(case.image, "native-cpp", case.canonical)
            reference_ok, reference_message, reference_ms = bridge_decode(case.image, "reference", case.canonical)
            rows.append({
                "geometry": geometry,
                "diameter_mm": diameter,
                "case": case.name,
                "native_ok": native_ok,
                "reference_ok": reference_ok,
                "both_ok": native_ok and reference_ok,
                "native_message": native_message,
                "reference_message": reference_message,
                "native_bridge_ms": native_ms,
                "reference_bridge_ms": reference_ms,
            })
    reference_failures = [row for row in rows if not row["reference_ok"]]
    output = {
        "schema_version": 1,
        "payload_bytes": len(PAYLOAD),
        "scope": "expanded digital-only matrix; native and reference decode the same transformed native PNG; bridge startup included",
        "total_cases": len(rows),
        "native_successes": sum(bool(row["native_ok"]) for row in rows),
        "reference_successes": sum(bool(row["reference_ok"]) for row in rows),
        "both_successes": sum(bool(row["both_ok"]) for row in rows),
        "pixel_metrics": pixels,
        "cases": rows,
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key not in {"cases", "pixel_metrics"}}, indent=2))
    if reference_failures:
        raise SystemExit(f"reference regressions: {reference_failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
