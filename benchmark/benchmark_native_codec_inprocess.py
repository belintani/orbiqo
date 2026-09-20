#!/usr/bin/env python3
"""Fair logical codec benchmark with process startup amortized.

Python work runs in this interpreter. C++ work runs repeatedly inside one
native benchmark process. PNG/SVG generation and image vision are excluded.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ROOT / "benchmark/fixtures/native_codec_draft06.json",
    ROOT / "benchmark/fixtures/native_codec_formats_1_5.json",
)
NATIVE_BENCH = ROOT / "server/python/native/orbiqo_codec_bench"
REPEATS = 1000
ECC = {"FAST": "fast", "BALANCED": "balanced", "ROBUST": "robust", "EXTREME": "extreme"}
PAYLOAD_TYPE = {"BINARY": "binary", "UTF8": "utf8", "URL": "url"}


def records() -> list[dict[str, object]]:
    return [
        record
        for fixture in FIXTURES
        for record in json.loads(fixture.read_text(encoding="utf-8"))["vectors"]
    ]


def python_encode_once(record: dict[str, object]) -> None:
    from radialcode.constants import Alphabet, EccLevel, PayloadType
    from radialcode.encoder import encode

    encode(
        bytes.fromhex(str(record["payload_hex"])),
        geometry=int(record["geometry_version"]),
        alphabet=Alphabet.COLOR4,
        ecc_level=EccLevel[str(record["ecc_level"])],
        palette_id=int(record["palette_id"]),
        payload_type=PayloadType[str(record["payload_type"])],
        compression=str(record["compression"]).lower(),
        format_version=int(record.get("format_version", 5)),
    )


def unpack_color4(record: dict[str, object]) -> list[int]:
    packed = bytes.fromhex(str(record["channel_symbols_packed_hex"]))
    count = int(record["channel_symbol_count"])
    symbols: list[int] = []
    for byte in packed:
        for shift in (6, 4, 2, 0):
            if len(symbols) == count:
                return symbols
            symbols.append((byte >> shift) & 0b11)
    return symbols


def python_decode_once(record: dict[str, object]) -> None:
    from radialcode.channel import decode_symbols
    from radialcode.constants import Alphabet, EccLevel
    from radialcode.ecc import decode as rs_decode, encoded_length
    from radialcode.framing import decode_frame
    from radialcode.geometry import geometry_for_format
    from radialcode.header import RadialHeader
    from radialcode.interleave import deinterleave_rs_blocks

    format_version = int(record.get("format_version", 5))
    ecc = EccLevel[str(record["ecc_level"])]
    frame_length = len(bytes.fromhex(str(record["frame_hex"])))
    geometry = geometry_for_format(int(record["geometry_version"]), format_version)
    header = RadialHeader(
        format_version=format_version,
        geometry_version=int(record["geometry_version"]),
        alphabet=Alphabet.COLOR4,
        palette_id=int(record["palette_id"]),
        ecc_level=ecc,
        mask_id=int(record["mask_id"]),
        encoded_payload_length=frame_length,
    )
    interleaved = decode_symbols(
        unpack_color4(record),
        geometry=geometry,
        alphabet=Alphabet.COLOR4,
        ecc_level=int(ecc),
        frame_length=frame_length,
        mask_id=header.mask_id,
        encoded_byte_length=encoded_length(frame_length, ecc),
    )
    concatenated = deinterleave_rs_blocks(interleaved, data_length=frame_length, level=ecc)
    frame = rs_decode(concatenated, data_length=frame_length, level=ecc).data
    decode_frame(frame)


def python_mean_ms(function, record: dict[str, object]) -> float:
    started = time.perf_counter()
    for _ in range(REPEATS):
        function(record)
    return (time.perf_counter() - started) * 1000.0 / REPEATS


def native_mean(record: dict[str, object]) -> dict[str, float]:
    command = [
        str(NATIVE_BENCH),
        str(record["payload_hex"]),
        str(record["geometry_version"]),
        ECC[str(record["ecc_level"])],
        PAYLOAD_TYPE[str(record["payload_type"])],
        str(record["compression"]).lower(),
        str(record["palette_id"]),
        str(record.get("format_version", 5)),
        str(REPEATS),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    values: dict[str, float] = {}
    for line in completed.stdout.splitlines():
        key, value = line.split("=", 1)
        if key.endswith("_ms"):
            values[key] = float(value)
    return values


def main() -> int:
    if not NATIVE_BENCH.exists():
        raise SystemExit(f"missing {NATIVE_BENCH}; run make -C server/python/native")
    print("name,format,geometry,python_encode_ms,cpp_encode_ms,encode_delta_percent,python_decode_ms,cpp_decode_ms,decode_delta_percent,repeats")
    for record in records():
        python_encode_ms = python_mean_ms(python_encode_once, record)
        python_decode_ms = python_mean_ms(python_decode_once, record)
        native = native_mean(record)
        encode_delta = (native["encode_mean_ms"] / python_encode_ms - 1.0) * 100.0
        decode_delta = (native["decode_mean_ms"] / python_decode_ms - 1.0) * 100.0
        print(
            f"{record['name']},{record.get('format_version', 5)},{record['geometry_version']},"
            f"{python_encode_ms:.3f},{native['encode_mean_ms']:.3f},{encode_delta:+.1f},"
            f"{python_decode_ms:.3f},{native['decode_mean_ms']:.3f},{decode_delta:+.1f},{REPEATS}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
