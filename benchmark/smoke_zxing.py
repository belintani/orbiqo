#!/usr/bin/env python3
"""Round-trip QR and Aztec through the installed ZXing-C++ binding."""

from __future__ import annotations

from importlib.metadata import version
import json

import numpy as np
from PIL import Image
import zxingcpp


def main() -> None:
    payload = b"orbiqo benchmark smoke"
    rows = []
    for name, barcode_format in (
        ("qr", zxingcpp.BarcodeFormat.QRCode),
        ("aztec", zxingcpp.BarcodeFormat.Aztec),
    ):
        barcode = zxingcpp.create_barcode(payload, barcode_format)
        image = zxingcpp.write_barcode_to_image(barcode, scale=8, add_quiet_zones=True)
        array = np.asarray(image)
        decoded = zxingcpp.read_barcode(array, formats=barcode_format, is_pure=True)
        rows.append(
            {
                "format": name,
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "barcode_attributes": [item for item in dir(barcode) if not item.startswith("_")],
                "decoded_valid": bool(decoded and decoded.valid),
                "decoded_bytes_equal": bool(decoded and bytes(decoded.bytes) == payload),
                "decoded_text": decoded.text if decoded else None,
            }
        )
        Image.fromarray(array).save(f"benchmark/{name}_smoke.png")
    print(json.dumps({"zxing_cpp": version("zxing-cpp"), "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
