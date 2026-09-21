#!/usr/bin/env python3
"""Measure native versus reference production across output resolutions.

The benchmark runs on one local machine. It is intended to add resolution
coverage, not to claim cross-machine performance.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "server/python/native/orbiqo_native"
sys.path.insert(0, str(ROOT / "server/python/vendor/radialcode/src"))
from radialcode.constants import Alphabet, EccLevel, PayloadType  # noqa: E402
from radialcode.decoder import decode_canonical  # noqa: E402
from radialcode.encoder import encode  # noqa: E402
from radialcode.renderer import RenderOptions, render_png_fast  # noqa: E402

PAYLOAD = bytes((index * 37 + 11) % 256 for index in range(67))
RUNS = 5
RESOLUTIONS = (300, 450, 600)
CASES = ((1, 30.0, "small"), (2, 40.0, "medium"))


def native_call(lines: list[str]) -> dict[str, str]:
    completed = subprocess.run(
        [str(NATIVE)],
        input=("\n".join(lines) + "\n").encode("ascii"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"native call failed with exit {completed.returncode}: "
            f"{completed.stderr.decode('utf-8', errors='replace')[:500]}"
        )
    result: dict[str, str] = {}
    for line in completed.stdout.decode("utf-8").splitlines():
        if line in ("ORBIQO_NATIVE_RESULT_V1", "END") or not line:
            continue
        key, value = line.split(" ", 1)
        result[key] = value
    return result


def native_generate(geometry: int, diameter: float, dpi: int) -> bytes:
    result = native_call([
        "OP generate",
        f"PAYLOAD_HEX {PAYLOAD.hex()}",
        f"GEOMETRY {geometry}",
        "FORMAT 5",
        "ALPHABET color4",
        "PAYLOAD_TYPE binary",
        "ECC balanced",
        "COMPRESSION none",
        "PALETTE 0",
        f"DPI {dpi}",
        f"DIAMETER_MM {diameter}",
        "RADIAL_FILL 0.78",
        "ANGULAR_FILL 0.78",
        "BACKGROUND #ffffff",
        "END",
    ])
    return base64.b64decode(result["png_base64"], validate=True)


def native_decode(png: bytes) -> bytes:
    result = native_call([
        "OP decode",
        f"IMAGE_HEX {png.hex()}",
        "CANONICAL 1",
        "ERASURE_THRESHOLD 0.55",
        "END",
    ])
    return bytes.fromhex(result["payload_hex"])


def median(values: list[float]) -> float:
    return statistics.median(values)


def main() -> int:
    rows: list[dict[str, object]] = []
    for dpi in RESOLUTIONS:
        for geometry, diameter, geometry_name in CASES:
            python_encode: list[float] = []
            cpp_encode: list[float] = []
            python_decode: list[float] = []
            cpp_decode: list[float] = []
            reference_png: bytes | None = None
            for _ in range(RUNS):
                started = time.perf_counter()
                symbol = encode(
                    PAYLOAD,
                    payload_type=PayloadType.BINARY,
                    geometry=geometry,
                    diameter_mm=diameter,
                    alphabet=Alphabet.COLOR4,
                    ecc_level=EccLevel.BALANCED,
                    compression="none",
                )
                reference_png = render_png_fast(
                    symbol,
                    dpi=dpi,
                    options=RenderOptions(radial_fill=0.78, angular_fill=0.78),
                )
                python_encode.append((time.perf_counter() - started) * 1000.0)
            assert reference_png is not None
            assert decode_canonical(reference_png).payload == PAYLOAD
            for _ in range(RUNS):
                started = time.perf_counter()
                native_png = native_generate(geometry, diameter, dpi)
                cpp_encode.append((time.perf_counter() - started) * 1000.0)
                assert native_decode(native_png) == PAYLOAD
            for _ in range(RUNS):
                started = time.perf_counter()
                assert decode_canonical(reference_png).payload == PAYLOAD
                python_decode.append((time.perf_counter() - started) * 1000.0)
            for _ in range(RUNS):
                started = time.perf_counter()
                assert native_decode(reference_png) == PAYLOAD
                cpp_decode.append((time.perf_counter() - started) * 1000.0)
            py_encode_median = median(python_encode)
            cpp_encode_median = median(cpp_encode)
            py_decode_median = median(python_decode)
            cpp_decode_median = median(cpp_decode)
            rows.append({
                "geometry": geometry_name,
                "geometry_id": geometry,
                "diameter_mm": diameter,
                "dpi": dpi,
                "runs": RUNS,
                "python_encode_render_median_ms": py_encode_median,
                "cpp_encode_render_process_median_ms": cpp_encode_median,
                "encode_render_delta_percent": (cpp_encode_median - py_encode_median) / py_encode_median * 100.0,
                "python_decode_median_ms": py_decode_median,
                "cpp_decode_process_median_ms": cpp_decode_median,
                "decode_delta_percent": (cpp_decode_median - py_decode_median) / py_decode_median * 100.0,
                "png_width": Image.open(BytesIO(reference_png)).width,
                "png_height": Image.open(BytesIO(reference_png)).height,
                "scope": "digital PNG; native process startup included; same payload and geometry; one local machine",
            })
    output = {
        "schema_version": 1,
        "payload_bytes": len(PAYLOAD),
        "resolutions_dpi": list(RESOLUTIONS),
        "runs_per_case": RUNS,
        "machine": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "scope": "production encode/render and canonical decode across resolutions; digital PNG; one local machine; process startup included for C++",
        "rows": rows,
    }
    result_path = ROOT / "benchmark/results/native_full_resolutions.json"
    result_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
