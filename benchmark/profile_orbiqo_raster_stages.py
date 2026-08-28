"""Profile the reference Orbiqo path from encoding through PNG-ready raster output.

This does not replace the normalized cross-format benchmark. It isolates the
reference renderer stages so a future native renderer can be compared against
the same payload, geometry, DPI and output size.
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
RADIAL_ROOT = Path(os.environ.get("ORBIQO_RADIALCODE_ROOT", ROOT / "server" / "python" / "vendor" / "radialcode")).resolve()
sys.path.insert(0, str(RADIAL_ROOT / "src"))

import radialcode
from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png_fast


OUTPUT = ROOT / "benchmark" / "results" / "orbiqo_raster_stage_profile.json"
PAYLOAD = bytes(((index * 73 + 19) % 256) for index in range(64))
RUNS = 10
DPI = 725
SUPERSAMPLE = 2


def median_ms(values: list[float]) -> float:
    return statistics.median(values)


def normalize_fixed(image: Image.Image) -> Image.Image:
    symbol = image.convert("RGB").resize((900, 900), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (1024, 1024), "white")
    canvas.paste(symbol, (62, 62))
    return canvas


def main() -> None:
    encode_times: list[float] = []
    raster_times: list[float] = []
    decode_png_times: list[float] = []
    normalize_times: list[float] = []
    total_times: list[float] = []

    for _ in range(RUNS):
        started = perf_counter()
        symbol = encode(
            PAYLOAD,
            payload_type=PayloadType.BINARY,
            geometry="auto",
            diameter_mm=30.0,
            alphabet=Alphabet.COLOR4,
            ecc_level=EccLevel.BALANCED,
            compression="none",
        )
        encode_times.append((perf_counter() - started) * 1000.0)

        started = perf_counter()
        png = render_png_fast(symbol, dpi=DPI, options=RenderOptions(center_text="OQ"), supersample=SUPERSAMPLE)
        raster_times.append((perf_counter() - started) * 1000.0)

        started = perf_counter()
        native = Image.open(BytesIO(png)).convert("RGB")
        decode_png_times.append((perf_counter() - started) * 1000.0)

        started = perf_counter()
        normalized = normalize_fixed(native)
        normalize_times.append((perf_counter() - started) * 1000.0)
        if normalized.size != (1024, 1024):
            raise AssertionError("normalized output dimensions drifted")

        total_times.append(encode_times[-1] + raster_times[-1] + decode_png_times[-1] + normalize_times[-1])

    result = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version.split()[0], "radialcode": radialcode.__version__},
        "method": {
            "payload_bytes": len(PAYLOAD),
            "ecc": "balanced",
            "geometry": "auto",
            "diameter_mm": 30.0,
            "dpi": DPI,
            "supersample": SUPERSAMPLE,
            "runs": RUNS,
            "scope": "sequential reference stages for a PNG-ready raster; not a cross-format benchmark",
        },
        "median_ms": {
            "encoder_core": median_ms(encode_times),
            "direct_png_renderer": median_ms(raster_times),
            "png_open_convert": median_ms(decode_png_times),
            "normalize_canvas": median_ms(normalize_times),
            "sequential_total": median_ms(total_times),
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
