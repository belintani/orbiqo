#!/usr/bin/env python3
"""Integration gate for the full native C++ encode/render/decode path."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "server/python/native/orbiqo_native"
PAYLOAD = b"orbiqo"

sys.path.insert(0, str(ROOT / "server/python/vendor/radialcode/src"))
from radialcode.decoder import decode_canonical


def run_native(lines: list[str]) -> dict[str, str]:
    completed = subprocess.run(
        [str(NATIVE)],
        input=("\n".join(lines) + "\n").encode("ascii"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    result: dict[str, str] = {}
    for line in completed.stdout.decode("utf-8").splitlines():
        if line in ("ORBIQO_NATIVE_RESULT_V1", "END") or not line:
            continue
        key, value = line.split(" ", 1)
        result[key] = value
    return result


def decode_native(png: bytes, canonical: bool = True) -> dict[str, str]:
    return run_native([
        "OP decode",
        f"IMAGE_HEX {png.hex()}",
        f"CANONICAL {1 if canonical else 0}",
        "ERASURE_THRESHOLD 0.55",
        "END",
    ])


def render_center_image() -> bytes:
    image = Image.new("RGBA", (96, 96), (240, 200, 8, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 12, 84, 84), fill=(0, 166, 214, 255))
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def main() -> None:
    if not NATIVE.is_file():
        raise AssertionError(f"missing native executable: {NATIVE}")
    cases = [
        (0, 5, 16.0),
        (1, 5, 30.0),
        (2, 5, 40.0),
        (3, 5, 50.0),
        (4, 5, 70.0),
        (5, 5, 18.0),
        (6, 5, 16.0),
        (1, 1, 30.0),
    ]
    center_image = render_center_image()
    for geometry, format_version, diameter in cases:
        result = run_native([
            "OP generate",
            f"PAYLOAD_HEX {PAYLOAD.hex()}",
            f"GEOMETRY {geometry}",
            f"FORMAT {format_version}",
            "ALPHABET color4",
            "PAYLOAD_TYPE binary",
            "ECC fast",
            "COMPRESSION none",
            "PALETTE 0",
            "DPI 600",
            f"DIAMETER_MM {diameter}",
            "RADIAL_FILL 0.80",
            "ANGULAR_FILL 0.82",
            "BACKGROUND #ffffff",
            "CENTER_TEXT_B64",
            "END",
        ])
        assert int(result["geometry_version"]) == geometry
        assert int(result["format_version"]) == format_version
        png = base64.b64decode(result["png_base64"], validate=True)
        svg = base64.b64decode(result["svg_base64"], validate=True)
        assert svg.startswith(b"<?xml")
        decoded = decode_native(png)
        assert bytes.fromhex(decoded["payload_hex"]) == PAYLOAD, (geometry, decoded)
        assert decoded["geometry_version"] == str(geometry)
        assert decoded["format_version"] == str(format_version)
        reference_decoded = decode_canonical(png)
        assert reference_decoded.payload == PAYLOAD, (geometry, reference_decoded.diagnostics)

    center_result = run_native([
        "OP generate",
        f"PAYLOAD_HEX {PAYLOAD.hex()}",
        "GEOMETRY 1",
        "FORMAT 5",
        "ALPHABET color4",
        "PAYLOAD_TYPE binary",
        "ECC fast",
        "COMPRESSION none",
        "PALETTE 2",
        "DPI 300",
        "DIAMETER_MM 30",
        "RADIAL_FILL 0.80",
        "ANGULAR_FILL 0.82",
        "BACKGROUND #ffffff",
        "CENTER_TEXT_B64 T1I=",
        "END",
    ])
    center_png = base64.b64decode(center_result["png_base64"], validate=True)
    assert bytes.fromhex(decode_native(center_png)["payload_hex"]) == PAYLOAD
    assert decode_canonical(center_png).payload == PAYLOAD
    image_result = run_native([
        "OP generate",
        f"PAYLOAD_HEX {PAYLOAD.hex()}",
        "GEOMETRY 1",
        "FORMAT 5",
        "ALPHABET color4",
        "PAYLOAD_TYPE binary",
        "ECC fast",
        "COMPRESSION none",
        "PALETTE 2",
        "DPI 300",
        "DIAMETER_MM 30",
        "RADIAL_FILL 0.80",
        "ANGULAR_FILL 0.82",
        "BACKGROUND #ffffff",
        f"CENTER_IMAGE_HEX {center_image.hex()}",
        "END",
    ])
    image_png = base64.b64decode(image_result["png_base64"], validate=True)
    assert bytes.fromhex(decode_native(image_png)["payload_hex"]) == PAYLOAD
    assert decode_canonical(image_png).payload == PAYLOAD
    print(json.dumps({"cases": len(cases), "center_text": True, "center_image": True, "status": "passed"}))


if __name__ == "__main__":
    main()
