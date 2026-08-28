#!/usr/bin/env python3
"""Inspect creator option names and verify fixed-version kwargs."""

from __future__ import annotations

import json

import zxingcpp


def main() -> None:
    option_names = [name for name in dir(zxingcpp) if "option" in name.lower()]
    attempts = []
    for format_name, barcode_format in (("qr", zxingcpp.BarcodeFormat.QRCode), ("aztec", zxingcpp.BarcodeFormat.Aztec)):
        for kwargs in ({"version": 1}, {"ec_level": "M"}, {"size_hint": 1}):
            try:
                barcode = zxingcpp.create_barcode("option probe", barcode_format, **kwargs)
                attempts.append({"format": format_name, "kwargs": kwargs, "ok": True, "ec_level": barcode.ec_level})
            except Exception as exc:
                attempts.append({"format": format_name, "kwargs": kwargs, "ok": False, "error": str(exc)})
    print(
        json.dumps(
            {
                "option_names": option_names,
                "option_docs": {name: getattr(zxingcpp, name).__doc__ for name in option_names},
                "attempts": attempts,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
