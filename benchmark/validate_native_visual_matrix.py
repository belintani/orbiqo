#!/usr/bin/env python3
"""Digital visual/degradation matrix for Python reference versus native C++."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "server/python/orbiqo_bridge.py"
REFERENCE_SRC = ROOT / "server/python/vendor/radialcode/src"
sys.path.insert(0, str(REFERENCE_SRC))
from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png_fast

PAYLOAD = bytes((index * 37 + 11) % 256 for index in range(67))
EXPECTED_PAYLOAD_B64 = base64.b64encode(PAYLOAD).decode("ascii")


@dataclass(frozen=True)
class Case:
    name: str
    image: bytes
    canonical: bool


def bridge_decode(image: bytes, backend: str, canonical: bool) -> tuple[bool, str, float]:
    request = {
        "op": "decode",
        "image_base64": base64.b64encode(image).decode("ascii"),
        "canonical": canonical,
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
        env={**__import__("os").environ, "ORBIQO_RADIALCODE_ROOT": str(ROOT / "server/python/vendor/radialcode")},
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


def encode_native(geometry: int, diameter: float) -> bytes:
    lines = [
        "OP generate",
        f"PAYLOAD_HEX {PAYLOAD.hex()}",
        f"GEOMETRY {geometry}",
        "FORMAT 5",
        "ALPHABET color4",
        "PAYLOAD_TYPE binary",
        "ECC balanced",
        "COMPRESSION none",
        "PALETTE 0",
        "DPI 600",
        f"DIAMETER_MM {diameter}",
        "RADIAL_FILL 0.78",
        "ANGULAR_FILL 0.78",
        "BACKGROUND #ffffff",
        "END",
    ]
    completed = subprocess.run(
        [str(ROOT / "server/python/native/orbiqo_native")],
        input=("\n".join(lines) + "\n").encode("ascii"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=120,
    )
    fields: dict[str, str] = {}
    for line in completed.stdout.decode("utf-8").splitlines():
        if line in ("ORBIQO_NATIVE_RESULT_V1", "END") or not line:
            continue
        key, value = line.split(" ", 1)
        fields[key] = value
    return base64.b64decode(fields["png_base64"], validate=True)


def python_reference(geometry: int, diameter: float) -> bytes:
    symbol = encode(
        PAYLOAD,
        payload_type=PayloadType.BINARY,
        geometry=geometry,
        diameter_mm=diameter,
        alphabet=Alphabet.COLOR4,
        ecc_level=EccLevel.BALANCED,
        compression="none",
    )
    return render_png_fast(symbol, dpi=600, options=RenderOptions(radial_fill=0.78, angular_fill=0.78))


def perspective(image: bytes, strength: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = source.shape[:2]
    margin_x = width * (0.06 + strength * 0.04)
    margin_y = height * (0.04 + strength * 0.05)
    source_points = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    target_points = np.float32([
        [margin_x, margin_y * 0.5],
        [width - margin_x * 0.25, margin_y * 1.6],
        [width - margin_x * 1.7, height - margin_y * 0.3],
        [margin_x * 0.4, height - margin_y * 1.2],
    ])
    transform = cv2.getPerspectiveTransform(source_points, target_points)
    warped = cv2.warpPerspective(source, transform, (width, height), borderValue=(255, 255, 255))
    ok, encoded = cv2.imencode(".png", warped)
    assert ok
    return encoded.tobytes()


def gaussian_noise(image: bytes, sigma: float) -> bytes:
    source = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR).astype(np.float32)
    rng = np.random.default_rng(1234 + int(sigma))
    noisy = np.clip(source + rng.normal(0.0, sigma, source.shape), 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".png", noisy)
    assert ok
    return encoded.tobytes()


def recompress(image: bytes, kind: str, quality: int) -> bytes:
    loaded = Image.open(BytesIO(image)).convert("RGB")
    out = BytesIO()
    loaded.save(out, format=kind, quality=quality, method=6 if kind == "WEBP" else 4)
    return out.getvalue()


def occlude(image: bytes, position: tuple[float, float], fraction: float = 0.06) -> bytes:
    loaded = Image.open(BytesIO(image)).convert("RGB")
    width, height = loaded.size
    side = int((width * height * fraction) ** 0.5)
    center_x, center_y = int(width * position[0]), int(height * position[1])
    draw = ImageDraw.Draw(loaded)
    draw.rectangle((center_x - side // 2, center_y - side // 2, center_x + side // 2, center_y + side // 2), fill=(255, 255, 255))
    out = BytesIO()
    loaded.save(out, format="PNG")
    return out.getvalue()


def pixel_metrics(native_png: bytes, reference_png: bytes) -> dict[str, float | int]:
    native = np.asarray(Image.open(BytesIO(native_png)).convert("RGB"), dtype=np.int16)
    reference = np.asarray(Image.open(BytesIO(reference_png)).convert("RGB"), dtype=np.int16)
    if native.shape != reference.shape:
        return {"same_shape": 0, "width": native.shape[1], "height": native.shape[0]}
    difference = np.abs(native - reference)
    squared = np.square(native.astype(np.float64) - reference.astype(np.float64))
    per_pixel = np.max(difference, axis=2)
    return {
        "same_shape": 1,
        "width": native.shape[1],
        "height": native.shape[0],
        "mae_rgb": float(np.mean(difference)),
        "rmse_rgb": float(np.sqrt(np.mean(squared))),
        "p95_max_channel_error": float(np.percentile(per_pixel, 95)),
        "pixels_with_max_error_le_16": float(np.mean(per_pixel <= 16.0)),
        "pixels_with_max_error_le_32": float(np.mean(per_pixel <= 32.0)),
    }


def main() -> None:
    rows: list[dict[str, object]] = []
    pixel_rows: list[dict[str, object]] = []
    for geometry, diameter in ((1, 30.0), (2, 40.0)):
        native_png = encode_native(geometry, diameter)
        reference_png = python_reference(geometry, diameter)
        pixel_rows.append({"geometry": geometry, "diameter_mm": diameter, **pixel_metrics(native_png, reference_png)})
        cases = [
            Case("clean-canonical", native_png, True),
            Case("clean-vision", native_png, False),
            Case("perspective-mild", perspective(native_png, 0.25), False),
            Case("perspective-medium", perspective(native_png, 0.60), False),
            Case("perspective-severe", perspective(native_png, 1.00), False),
            Case("noise-sigma-3", gaussian_noise(native_png, 3.0), False),
            Case("noise-sigma-8", gaussian_noise(native_png, 8.0), False),
            Case("jpeg-q95", recompress(native_png, "JPEG", 95), False),
            Case("jpeg-q80", recompress(native_png, "JPEG", 80), False),
            Case("webp-q90", recompress(native_png, "WEBP", 90), False),
            Case("webp-q70", recompress(native_png, "WEBP", 70), False),
            Case("occlusion-6-top-right", occlude(native_png, (0.73, 0.28)), False),
            Case("occlusion-6-bottom-left", occlude(native_png, (0.28, 0.73)), False),
        ]
        for case in cases:
            native_ok, native_message, native_ms = bridge_decode(case.image, "native-cpp", case.canonical)
            reference_ok, reference_message, reference_ms = bridge_decode(case.image, "reference", case.canonical)
            rows.append({
                "geometry": geometry,
                "diameter_mm": diameter,
                "case": case.name,
                "canonical": case.canonical,
                "native_ok": native_ok,
                "reference_ok": reference_ok,
                "both_ok": native_ok and reference_ok,
                "native_message": native_message,
                "reference_message": reference_message,
                "native_bridge_ms": native_ms,
                "reference_bridge_ms": reference_ms,
            })
    known_native_vision_limits = {"perspective-mild", "perspective-medium", "perspective-severe", "occlusion-6-top-right"}
    unexpected_reference_failures = [row for row in rows if not row["reference_ok"]]
    unexpected_native_failures = [row for row in rows if not row["native_ok"] and row["case"] not in known_native_vision_limits]
    if unexpected_reference_failures:
        raise AssertionError(f"reference regressions: {unexpected_reference_failures}")
    if unexpected_native_failures:
        raise AssertionError(f"unexpected native regressions: {unexpected_native_failures}")
    output = {
        "schema_version": 1,
        "payload_bytes": len(PAYLOAD),
        "scope": "digital-only; native and reference decode the same transformed image; bridge startup included",
        "pixel_metrics": pixel_rows,
        "cases": rows,
    }
    path = ROOT / "benchmark/results/native_visual_matrix.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
