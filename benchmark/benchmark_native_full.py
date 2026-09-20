#!/usr/bin/env python3
"""Measure full native versus reference production on identical PNG cases."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "server/python/native/orbiqo_native"
sys.path.insert(0, str(ROOT / "server/python/vendor/radialcode/src"))
from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.decoder import decode_canonical
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png_fast

PAYLOAD = bytes((index * 37 + 11) % 256 for index in range(67))
RUNS = 10


def native_call(lines: list[str]) -> dict[str, str]:
    completed = subprocess.run([str(NATIVE)], input=("\n".join(lines) + "\n").encode("ascii"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60)
    result: dict[str, str] = {}
    for line in completed.stdout.decode("utf-8").splitlines():
        if line in ("ORBIQO_NATIVE_RESULT_V1", "END") or not line:
            continue
        key, value = line.split(" ", 1)
        result[key] = value
    return result


def native_generate(geometry: int, diameter: float) -> bytes:
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
        "DPI 600",
        f"DIAMETER_MM {diameter}",
        "RADIAL_FILL 0.78",
        "ANGULAR_FILL 0.78",
        "BACKGROUND #ffffff",
        "END",
    ])
    return base64.b64decode(result["png_base64"], validate=True)


def native_decode(png: bytes) -> bytes:
    result = native_call(["OP decode", f"IMAGE_HEX {png.hex()}", "CANONICAL 1", "ERASURE_THRESHOLD 0.55", "END"])
    return bytes.fromhex(result["payload_hex"])


def median(values: list[float]) -> float:
    return statistics.median(values)


def main() -> None:
    rows = []
    for geometry, diameter in ((1, 30.0), (2, 40.0)):
        python_encode = []
        python_decode = []
        native_generate_times = []
        native_decode_times = []
        reference_png = None
        for _ in range(RUNS):
            started = time.perf_counter()
            symbol = encode(PAYLOAD, payload_type=PayloadType.BINARY, geometry=geometry, diameter_mm=diameter, alphabet=Alphabet.COLOR4, ecc_level=EccLevel.BALANCED, compression="none")
            reference_png = render_png_fast(symbol, dpi=600, options=RenderOptions(radial_fill=0.78, angular_fill=0.78))
            python_encode.append((time.perf_counter() - started) * 1000.0)
        assert reference_png is not None
        assert decode_canonical(reference_png).payload == PAYLOAD
        for _ in range(RUNS):
            started = time.perf_counter()
            native_png = native_generate(geometry, diameter)
            native_generate_times.append((time.perf_counter() - started) * 1000.0)
            assert native_decode(native_png) == PAYLOAD
        for _ in range(RUNS):
            started = time.perf_counter()
            assert decode_canonical(reference_png).payload == PAYLOAD
            python_decode.append((time.perf_counter() - started) * 1000.0)
        for _ in range(RUNS):
            started = time.perf_counter()
            assert native_decode(reference_png) == PAYLOAD
            native_decode_times.append((time.perf_counter() - started) * 1000.0)
        py_encode_median = median(python_encode)
        cpp_generate_median = median(native_generate_times)
        py_decode_median = median(python_decode)
        cpp_decode_median = median(native_decode_times)
        rows.append({
            "geometry": geometry,
            "diameter_mm": diameter,
            "runs": RUNS,
            "python_encode_render_median_ms": py_encode_median,
            "cpp_encode_render_process_median_ms": cpp_generate_median,
            "encode_render_delta_percent": (cpp_generate_median - py_encode_median) / py_encode_median * 100.0,
            "python_decode_median_ms": py_decode_median,
            "cpp_decode_process_median_ms": cpp_decode_median,
            "decode_delta_percent": (cpp_decode_median - py_decode_median) / py_decode_median * 100.0,
            "scope": "digital PNG; native process startup included; reference and native decode same Python-produced PNG",
        })
    output = {"schema_version": 1, "payload_bytes": len(PAYLOAD), "rows": rows}
    result_path = ROOT / "benchmark/results/native_full_comparison.json"
    result_path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
