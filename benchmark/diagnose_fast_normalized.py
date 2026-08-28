"""Diagnose normalized Orbiqo round trips by direct-raster supersampling level."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image

REFERENCE = Path(__file__).resolve().parents[2] / "radialcode"
sys.path.insert(0, str(REFERENCE / "src"))

from radialcode.constants import Alphabet, EccLevel, PayloadType  # noqa: E402
from radialcode.encoder import encode  # noqa: E402
from radialcode.renderer import RenderOptions, render_png_fast  # noqa: E402
from radialcode.vision import decode_image  # noqa: E402


CANVAS_SIZE = 1024
OCCUPIED_SIZE = 900
PAYLOAD = bytes(((index * 73 + 19) % 256) for index in range(64))


def normalize(image: Image.Image) -> Image.Image:
    resized = image.resize((OCCUPIED_SIZE, OCCUPIED_SIZE), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), "white")
    offset = (CANVAS_SIZE - OCCUPIED_SIZE) // 2
    canvas.paste(resized, (offset, offset))
    return canvas


def main() -> None:
    symbol = encode(
        PAYLOAD,
        payload_type=PayloadType.BINARY,
        geometry="auto",
        diameter_mm=30,
        alphabet=Alphabet.COLOR4,
        ecc_level=EccLevel.BALANCED,
        compression="none",
    )
    rows = []
    for dpi in (300, 724):
        for supersample in (1, 2, 3, 4):
            image = Image.open(BytesIO(render_png_fast(symbol, dpi=dpi, options=RenderOptions(center_text="OQ"), supersample=supersample))).convert("RGB")
            normalized = normalize(image)
            try:
                decoded = decode_image(normalized, output_size=1024)
                exact = decoded.decoded.payload == PAYLOAD
                error = ""
            except Exception as exc:
                exact = False
                error = f"{type(exc).__name__}: {exc}"
            rows.append({"dpi": dpi, "supersample": supersample, "native_size": list(image.size), "exact": exact, "error": error})
    output = Path(__file__).resolve().parent / "results" / "fast_normalized_diagnostic.json"
    output.write_text(json.dumps({"geometry": symbol.geometry.version.number, "rows": rows}, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
