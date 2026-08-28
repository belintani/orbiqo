"""Compare the Python reference raster renderer with the opt-in C++ prototype.

The C++ prototype receives an already encoded symbol. Timings therefore isolate
PNG-ready raster production, including its per-request executable launch, and
do not claim an end-to-end replacement for the full reference pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "server" / "python"
RADIAL_ROOT = Path(os.environ.get("ORBIQO_RADIALCODE_ROOT", BRIDGE_DIR / "vendor" / "radialcode")).resolve()
sys.path.insert(0, str(RADIAL_ROOT / "src"))
sys.path.insert(0, str(BRIDGE_DIR))

from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.decoder import decode_canonical
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png_fast
import orbiqo_bridge


OUTPUT = ROOT / "benchmark" / "results" / "native_renderer_comparison.json"
PAYLOAD = b"Orbiqo native renderer parity payload / 64 byte fixture: 2026-alpha"
RUNS = 10
DPI = 600
CASES = (
    ("micro-4", 18.0),
    ("small", 30.0),
    ("medium", 42.0),
)


def median_ms(values: list[float]) -> float:
    return statistics.median(values)


def decode_output(png: bytes) -> bytes:
    with Image.open(BytesIO(png)) as image:
        canonical = image.convert("RGB")
        return decode_canonical(canonical).payload


def measure(renderer, symbol, options: RenderOptions) -> tuple[float, bytes]:
    started = perf_counter()
    output = renderer(symbol, dpi=DPI, options=options)
    return (perf_counter() - started) * 1000.0, output


def main() -> None:
    native_path = BRIDGE_DIR / "native" / "orbiqo_renderer"
    if not native_path.is_file():
        raise SystemExit(f"native renderer must be compiled first: {native_path}")
    options = RenderOptions(center_text=None, center_image_png=None, angular_fill=0.82, radial_fill=0.80)
    cases = []
    for geometry, diameter_mm in CASES:
        symbol = encode(
            PAYLOAD,
            payload_type=PayloadType.BINARY,
            geometry=geometry,
            diameter_mm=diameter_mm,
            alphabet=Alphabet.COLOR4,
            ecc_level=EccLevel.BALANCED,
            palette_id=0,
            compression="none",
        )
        reference_runs: list[float] = []
        native_runs: list[float] = []
        native_png = b""
        reference_png = b""
        for _ in range(RUNS):
            reference_time, reference_png = measure(render_png_fast, symbol, options)
            reference_runs.append(reference_time)
            native_time, native_png = measure(orbiqo_bridge._render_png_native, symbol, options)  # noqa: SLF001
            native_runs.append(native_time)
        if decode_output(reference_png) != PAYLOAD:
            raise AssertionError(f"reference renderer failed canonical decode for {geometry}")
        if decode_output(native_png) != PAYLOAD:
            raise AssertionError(f"native renderer failed canonical decode for {geometry}")
        cases.append(
            {
                "geometry": geometry,
                "diameter_mm": diameter_mm,
                "native_output_bytes": len(native_png),
                "reference_output_bytes": len(reference_png),
                "reference_renderer_median_ms": median_ms(reference_runs),
                "native_renderer_median_ms": median_ms(native_runs),
                "native_relative_change_percent": ((median_ms(native_runs) / median_ms(reference_runs)) - 1.0) * 100.0,
                "reference_roundtrip": True,
                "native_roundtrip": True,
            }
        )
    result = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "runs": RUNS,
            "dpi": DPI,
            "payload_bytes": len(PAYLOAD),
            "ecc": "balanced",
            "identity": "pulse-equivalent fills, empty center",
            "scope": "PNG-ready renderer comparison only; C++ process launch is included; Python remains the reference encoder and decoder",
        },
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
