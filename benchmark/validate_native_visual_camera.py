#!/usr/bin/env python3
"""Camera-like digital stress matrix for native C++ versus the Python oracle.

This is a deterministic synthetic camera pipeline, not a claim about physical
camera performance. It combines resampling, color response, illumination,
noise, compression, and non-rectangular occlusion over the same native PNG.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
from validate_native_visual_matrix import (  # noqa: E402
    EXPECTED_PAYLOAD_B64,
    PAYLOAD,
    encode_native,
    pixel_metrics,
    python_reference,
)

BRIDGE = ROOT / "server/python/orbiqo_bridge.py"
OUTPUT = ROOT / "benchmark/results/native_visual_camera.json"


@dataclass(frozen=True)
class Case:
    name: str
    image: bytes
    canonical: bool = False


def encode_png(array: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", array)
    assert ok
    return encoded.tobytes()


def camera_resample(image: bytes, scale: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = source.shape[:2]
    small = cv2.resize(
        source,
        (max(48, int(width * scale)), max(48, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    restored = cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)
    return encode_png(restored)


def camera_color_response(image: bytes, gains: tuple[float, float, float], gamma: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR).astype(np.float32) / 255.0
    adjusted = np.empty_like(source)
    for channel, gain in enumerate(gains):
        adjusted[:, :, channel] = np.clip(np.power(source[:, :, channel], gamma) * gain, 0.0, 1.0)
    return encode_png(np.round(adjusted * 255.0).astype(np.uint8))


def vignette(image: bytes, strength: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR).astype(np.float32)
    height, width = source.shape[:2]
    y, x = np.ogrid[:height, :width]
    dx = (x - width / 2.0) / (width / 2.0)
    dy = (y - height / 2.0) / (height / 2.0)
    radius = np.sqrt(dx * dx + dy * dy)
    gain = np.clip(1.0 - strength * np.maximum(radius - 0.20, 0.0), 0.48, 1.0)
    return encode_png(np.clip(source * gain[:, :, None], 0, 255).astype(np.uint8))


def sensor_noise(image: bytes, sigma: float, seed: int) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR).astype(np.float32)
    rng = np.random.default_rng(seed)
    noisy = source + rng.normal(0.0, sigma, source.shape)
    return encode_png(np.clip(noisy, 0, 255).astype(np.uint8))


def camera_pipeline(image: bytes) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = source.shape[:2]
    small = cv2.resize(source, (int(width * 0.72), int(height * 0.72)), interpolation=cv2.INTER_AREA)
    restored = cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    restored = np.clip(restored * np.array([1.04, 0.99, 0.92], dtype=np.float32), 0, 255)
    rng = np.random.default_rng(90210)
    restored += rng.normal(0.0, 3.5, restored.shape)
    restored = np.clip(restored + 8.0, 0, 255).astype(np.uint8)
    encoded = cv2.imencode(".jpg", restored, [cv2.IMWRITE_JPEG_QUALITY, 72])[1]
    return encoded.tobytes()


def nonrectangular_occlusion(image: bytes, shape: str, center: tuple[float, float], fraction: float) -> bytes:
    loaded = Image.open(BytesIO(image)).convert("RGB")
    width, height = loaded.size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    center_x, center_y = int(width * center[0]), int(height * center[1])
    area = width * height * fraction
    if shape == "circle":
        radius = int(np.sqrt(area / np.pi))
        draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=255)
    elif shape == "ellipse":
        semi_major = int(np.sqrt(area * 2.4 / np.pi))
        semi_minor = max(3, int(area / (np.pi * semi_major)))
        draw.ellipse((center_x - semi_major, center_y - semi_minor, center_x + semi_major, center_y + semi_minor), fill=255)
    elif shape == "rounded-strip":
        strip_width = max(6, int(np.sqrt(area * 2.8)))
        strip_height = max(6, int(area / strip_width))
        draw.rounded_rectangle(
            (center_x - strip_width // 2, center_y - strip_height // 2, center_x + strip_width // 2, center_y + strip_height // 2),
            radius=max(4, strip_height // 3),
            fill=255,
        )
    else:
        raise ValueError(f"unknown occlusion shape: {shape}")
    white = Image.new("RGB", (width, height), (255, 255, 255))
    result = Image.composite(white, loaded, mask)
    out = BytesIO()
    result.save(out, format="PNG")
    return out.getvalue()


def glare(image: bytes) -> bytes:
    loaded = Image.open(BytesIO(image)).convert("RGB")
    overlay = Image.new("RGBA", loaded.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = loaded.size
    draw.rounded_rectangle(
        (int(width * 0.54), int(height * 0.12), int(width * 0.82), int(height * 0.28)),
        radius=int(height * 0.05),
        fill=(255, 255, 255, 190),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=max(2, int(width * 0.006))))
    result = Image.alpha_composite(loaded.convert("RGBA"), overlay).convert("RGB")
    out = BytesIO()
    result.save(out, format="JPEG", quality=92)
    return out.getvalue()


def bridge_decode(image: bytes, backend: str) -> tuple[bool, str, float]:
    request = {
        "op": "decode",
        "image_base64": base64.b64encode(image).decode("ascii"),
        "canonical": False,
        "output_size": 1024,
        "erasure_threshold": 0.55,
        "decoder_backend": backend,
    }
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, str(BRIDGE)],
        input=(json.dumps(request) + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
        env={
            **__import__("os").environ,
            "ORBIQO_RADIALCODE_ROOT": str(ROOT / "server/python/vendor/radialcode"),
        },
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    try:
        response = json.loads(completed.stdout.decode("utf-8"))
    except Exception:
        return False, f"invalid bridge output: {completed.stderr.decode('utf-8', errors='replace')[:180]}", elapsed
    if not response.get("ok"):
        return False, str(response.get("error", {}).get("message", "decode failed")), elapsed
    result = response["result"]
    return result.get("payload_base64") == EXPECTED_PAYLOAD_B64, "ok", elapsed


def cases(image: bytes) -> list[Case]:
    return [
        Case("camera-resample-0.72", camera_resample(image, 0.72)),
        Case("camera-color-warm-gamma", camera_color_response(image, (1.10, 1.02, 0.92), 1.04)),
        Case("camera-color-cool-gamma", camera_color_response(image, (0.92, 1.01, 1.10), 0.96)),
        Case("camera-vignette", vignette(image, 0.62)),
        Case("camera-sensor-noise", sensor_noise(image, 5.0, 20260921)),
        Case("camera-pipeline-jpeg", camera_pipeline(image)),
        Case("occlusion-circle-6", nonrectangular_occlusion(image, "circle", (0.72, 0.30), 0.06)),
        Case("occlusion-ellipse-6", nonrectangular_occlusion(image, "ellipse", (0.30, 0.70), 0.06)),
        Case("occlusion-rounded-strip-6", nonrectangular_occlusion(image, "rounded-strip", (0.70, 0.68), 0.06)),
        Case("glare-rounded", glare(image)),
    ]


def main() -> int:
    rows: list[dict[str, object]] = []
    pixels: list[dict[str, object]] = []
    for geometry, diameter in ((1, 30.0), (2, 40.0)):
        native_png = encode_native(geometry, diameter)
        reference_png = python_reference(geometry, diameter)
        pixels.append({"geometry": geometry, "diameter_mm": diameter, **pixel_metrics(native_png, reference_png)})
        for case in cases(native_png):
            native_ok, native_message, native_ms = bridge_decode(case.image, "native-cpp")
            reference_ok, reference_message, reference_ms = bridge_decode(case.image, "reference")
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
    native_failures = [row for row in rows if not row["native_ok"]]
    known_reference_limits = [
        row for row in reference_failures
        if row["geometry"] == 1 and row["case"] == "occlusion-circle-6"
    ]
    unexpected_reference_failures = [row for row in reference_failures if row not in known_reference_limits]
    output = {
        "schema_version": 1,
        "payload_bytes": len(PAYLOAD),
        "scope": "synthetic camera-like digital matrix; deterministic transformations; native and reference decode the same transformed native PNG; bridge startup included; not a physical-camera claim",
        "total_cases": len(rows),
        "native_successes": sum(bool(row["native_ok"]) for row in rows),
        "reference_successes": sum(bool(row["reference_ok"]) for row in rows),
        "both_successes": sum(bool(row["both_ok"]) for row in rows),
        "native_failure_cases": [row["case"] for row in native_failures],
        "reference_failure_cases": [row["case"] for row in reference_failures],
        "known_reference_limit_cases": [
            {"geometry": row["geometry"], "case": row["case"]} for row in known_reference_limits
        ],
        "pixel_metrics": pixels,
        "cases": rows,
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key not in {"cases", "pixel_metrics"}}, indent=2))
    if unexpected_reference_failures:
        raise SystemExit(f"unexpected reference regressions: {unexpected_reference_failures}")
    if native_failures:
        raise SystemExit(f"native failures: {native_failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
