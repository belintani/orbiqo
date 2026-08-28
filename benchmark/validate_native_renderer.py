"""Validate the opt-in C++ raster core against the Python reference decoder.

The C++ renderer receives symbols already encoded by RadialCode. This validation
exercises every current Draft 0.6 geometry with an empty center, the supported
scope of the native prototype, and persists exact-payload outcomes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "server" / "python"
RADIAL_ROOT = Path(os.environ.get("ORBIQO_RADIALCODE_ROOT", BRIDGE_DIR / "vendor" / "radialcode")).resolve()
sys.path.insert(0, str(RADIAL_ROOT / "src"))
sys.path.insert(0, str(BRIDGE_DIR))

from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.decoder import decode_canonical
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions
import orbiqo_bridge


OUTPUT = ROOT / "benchmark" / "results" / "native_renderer_validation.json"
CASES = (
    ("micro-1", 16.0, EccLevel.FAST, b"native-micro-1"),
    ("micro-2", 16.0, EccLevel.BALANCED, b"native-micro-2"),
    ("micro-4", 18.0, EccLevel.BALANCED, b"native-micro-4-payload"),
    ("small", 30.0, EccLevel.ROBUST, b"native-small-payload"),
    ("medium", 42.0, EccLevel.BALANCED, b"native-medium-payload"),
    ("large", 50.0, EccLevel.BALANCED, b"native-large-payload"),
    ("xl", 70.0, EccLevel.BALANCED, b"native-xl-payload"),
)


def decode_output(png: bytes, geometry_version: int) -> bytes:
    with Image.open(BytesIO(png)) as image:
        return decode_canonical(image.convert("RGB"), geometry_hint=geometry_version).payload


def main() -> None:
    native_path = BRIDGE_DIR / "native" / "orbiqo_renderer"
    if not native_path.is_file():
        raise SystemExit(f"native renderer must be compiled first: {native_path}")
    rows: list[dict[str, object]] = []
    for geometry, diameter_mm, ecc, payload in CASES:
        symbol = encode(
            payload,
            payload_type=PayloadType.BINARY,
            geometry=geometry,
            diameter_mm=diameter_mm,
            alphabet=Alphabet.COLOR4,
            ecc_level=ecc,
            palette_id=0,
            compression="none",
        )
        png = orbiqo_bridge._render_png_native(  # noqa: SLF001
            symbol,
            dpi=600,
            options=RenderOptions(center_text=None, center_image_png=None, angular_fill=0.82, radial_fill=0.80),
        )
        decoded = decode_output(png, symbol.geometry.version.number)
        rows.append(
            {
                "geometry": geometry,
                "geometry_version": symbol.geometry.version.number,
                "ecc": ecc.name,
                "diameter_mm": diameter_mm,
                "png_bytes": len(png),
                "exact_payload": decoded == payload,
            }
        )
    if not all(bool(row["exact_payload"]) for row in rows):
        raise AssertionError("native renderer failed at least one exact-payload case")
    result = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Draft 0.6 empty-center native core only; exact canonical decode through the Python reference decoder",
        "cases": rows,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
