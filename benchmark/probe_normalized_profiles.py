#!/usr/bin/env python3
"""Probe supported ECC controls and logical matrix sizes for normalized profiles."""

from __future__ import annotations

import json

import numpy as np
import zxingcpp


PAYLOAD = bytes(((index * 73 + 19) % 256) for index in range(64))


def probe(format_name: str, barcode_format: zxingcpp.BarcodeFormat, levels: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for level in levels:
        try:
            barcode = zxingcpp.create_barcode(PAYLOAD, barcode_format, ec_level=level)
            matrix = np.asarray(zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=True))
            rows.append(
                {
                    "format": format_name,
                    "requested_ec_level": level,
                    "reported_ec_level": barcode.ec_level,
                    "width_modules_with_quiet_zone": int(matrix.shape[1]),
                    "height_modules_with_quiet_zone": int(matrix.shape[0]),
                }
            )
        except Exception as exc:
            rows.append({"format": format_name, "requested_ec_level": level, "error": str(exc)})
    return rows


def main() -> None:
    rows = probe("qr", zxingcpp.BarcodeFormat.QRCode, ["L", "M", "Q", "H"])
    rows.extend(probe("aztec", zxingcpp.BarcodeFormat.Aztec, ["10", "15", "20", "25", "30", "33", "40", "50"]))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
