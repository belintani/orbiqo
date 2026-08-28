#!/usr/bin/env python3
"""Inspect and smoke-test the installed ZXing-C++ Python API."""

from __future__ import annotations

from importlib.metadata import version
import inspect
import json

import zxingcpp


def signature(name: str) -> str:
    value = getattr(zxingcpp, name, None)
    if value is None:
        return "missing"
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return str(value.__doc__ or "builtin without signature").splitlines()[0]


def main() -> None:
    names = [name for name in dir(zxingcpp) if "barcode" in name.lower() or "write" in name.lower()]
    output = {
        "version": version("zxing-cpp"),
        "relevant_names": names,
        "signatures": {name: signature(name) for name in names},
        "docs": {
            name: getattr(zxingcpp, name).__doc__
            for name in ("create_barcode", "write_barcode_to_image", "write_barcode_to_svg", "read_barcode")
        },
        "formats": [name for name in dir(zxingcpp.BarcodeFormat) if not name.startswith("_")],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
