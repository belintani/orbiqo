#!/usr/bin/env python3
"""Parity gate for the native Orbiqo logical codec.

The Python reference remains the oracle. This test only promotes C++ when every
intermediate field matches a recorded vector and the native logical decoder
recovers the payload, including RS/BCH corruption checks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    ROOT / "benchmark/fixtures/native_codec_draft06.json",
    ROOT / "benchmark/fixtures/native_codec_formats_1_5.json",
)
BINARY = Path(os.environ.get("ORBIQO_CODEC_BINARY", ROOT / "server/python/native/orbiqo_codec"))
ECC = {"FAST": "fast", "BALANCED": "balanced", "ROBUST": "robust", "EXTREME": "extreme"}
PAYLOAD_TYPE = {"BINARY": "binary", "UTF8": "utf8", "URL": "url"}


def run(*args: str) -> dict[str, str]:
    completed = subprocess.run(
        [str(BINARY), *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    result: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, value = line.split("=", 1)
        result[key] = value
    return result


def assert_equal(actual: dict[str, str], key: str, expected: str, name: str) -> None:
    if actual.get(key) != expected:
        raise AssertionError(f"{name}: {key}: expected {expected!r}, got {actual.get(key)!r}")


def main() -> int:
    if not BINARY.exists():
        raise SystemExit(f"missing native codec: {BINARY}; run make -C server/python/native")
    cases = [
        record
        for manifest_path in MANIFESTS
        for record in json.loads(manifest_path.read_text(encoding="utf-8"))["vectors"]
    ]
    for record in cases:
        name = str(record["name"])
        encoded = run(
            "encode",
            str(record["payload_hex"]),
            str(record["geometry_version"]),
            ECC[str(record["ecc_level"])],
            PAYLOAD_TYPE[str(record["payload_type"])],
            str(record["compression"]).lower(),
            str(record["palette_id"]),
            str(record.get("format_version", 5)),
        )
        for key in ("frame_hex", "rs_concatenated_hex", "rs_interleaved_hex", "channel_symbols_packed_hex", "mask_id", "header_data_hex", "header_codeword_hex"):
            assert_equal(encoded, key, str(record[key]), name)
        assert_equal(encoded, "channel_symbol_count", str(record["channel_symbol_count"]), name)
        assert_equal(encoded, "format_version", str(record.get("format_version", 5)), name)
        decoded = run(
            "decode",
            encoded["channel_symbols_packed_hex"],
            encoded["channel_symbol_count"],
            encoded["header_codeword_hex"],
        )
        assert_equal(decoded, "payload_hex", str(record["payload_hex"]), name)
        assert_equal(decoded, "frame_hex", str(record["frame_hex"]), name)
        assert_equal(decoded, "format_version", str(record.get("format_version", 5)), name)
        assert_equal(decoded, "geometry_version", str(record["geometry_version"]), name)
        assert_equal(decoded, "mask_id", str(record["mask_id"]), name)

        packed = bytearray.fromhex(encoded["channel_symbols_packed_hex"])
        positions = sorted({0, len(packed) // 3, (2 * len(packed)) // 3})
        for position in positions:
            packed[position] ^= 0x04
        repaired = run("decode", packed.hex(), encoded["channel_symbol_count"], encoded["header_codeword_hex"])
        assert_equal(repaired, "payload_hex", str(record["payload_hex"]), f"{name} three-symbol correction")

        header = int(encoded["header_codeword_hex"], 16) ^ 0x1
        repaired_header = run("decode", encoded["channel_symbols_packed_hex"], encoded["channel_symbol_count"], f"{header:016x}")
        assert_equal(repaired_header, "payload_hex", str(record["payload_hex"]), f"{name} BCH correction")

        print(f"PASS {name}")
    print(f"native codec parity: {len(cases)} vectors + RS/BCH corruption recovery")
    return 0


if __name__ == "__main__":
    sys.exit(main())
