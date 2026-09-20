#!/usr/bin/env python3
"""Measure logical codec work only; PNG/SVG and vision are intentionally excluded."""

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
REPEATS = 30


def python_encode(record: dict[str, object]) -> None:
    from radialcode.constants import Alphabet, EccLevel, PayloadType
    from radialcode.encoder import encode

    alphabet = Alphabet.COLOR4
    ecc = EccLevel[str(record["ecc_level"])]
    payload_type = PayloadType[str(record["payload_type"])]
    payload = bytes.fromhex(str(record["payload_hex"]))
    for _ in range(REPEATS):
        encode(
            payload,
            geometry=int(record["geometry_version"]),
            alphabet=alphabet,
            ecc_level=ecc,
            palette_id=int(record["palette_id"]),
            payload_type=payload_type,
            compression=str(record["compression"]).lower(),
            format_version=int(record.get("format_version", 5)),
        )


def native_encode(record: dict[str, object]) -> None:
    command = [
        str(ROOT / "server/python/native/orbiqo_codec"),
        "encode",
        str(record["payload_hex"]),
        str(record["geometry_version"]),
        str(record["ecc_level"]).lower(),
        str(record["payload_type"]).lower(),
        str(record["compression"]).lower(),
        str(record["palette_id"]),
        str(record.get("format_version", 5)),
    ]
    for _ in range(REPEATS):
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def python_decode(record: dict[str, object]) -> None:
    from radialcode.channel import decode_symbols
    from radialcode.constants import Alphabet, EccLevel
    from radialcode.ecc import decode as rs_decode
    from radialcode.ecc import encoded_length
    from radialcode.framing import decode_frame
    from radialcode.geometry import geometry_for_format
    from radialcode.header import RadialHeader
    from radialcode.interleave import deinterleave_rs_blocks

    packed = bytes.fromhex(str(record["channel_symbols_packed_hex"]))
    physical_symbols: list[int] = []
    for byte in packed:
        for shift in (6, 4, 2, 0):
            if len(physical_symbols) == int(record["channel_symbol_count"]):
                break
            physical_symbols.append((byte >> shift) & 0b11)
    ecc = EccLevel[str(record["ecc_level"])]
    format_version = int(record.get("format_version", 5))
    geometry = geometry_for_format(int(record["geometry_version"]), format_version)
    frame_length = len(bytes.fromhex(str(record["frame_hex"])))
    header = RadialHeader(
        format_version=format_version,
        geometry_version=int(record["geometry_version"]),
        alphabet=Alphabet.COLOR4,
        palette_id=int(record["palette_id"]),
        ecc_level=ecc,
        mask_id=int(record["mask_id"]),
        encoded_payload_length=frame_length,
    )
    rs_length = encoded_length(frame_length, ecc)
    for _ in range(REPEATS):
        interleaved = decode_symbols(
            physical_symbols,
            geometry=geometry,
            alphabet=Alphabet.COLOR4,
            ecc_level=int(ecc),
            frame_length=frame_length,
            mask_id=header.mask_id,
            encoded_byte_length=rs_length,
        )
        concatenated = deinterleave_rs_blocks(interleaved, data_length=frame_length, level=ecc)
        frame = rs_decode(concatenated, data_length=frame_length, level=ecc).data
        decode_frame(frame)


def native_decode(record: dict[str, object]) -> None:
    command = [
        str(ROOT / "server/python/native/orbiqo_codec"),
        "decode",
        str(record["channel_symbols_packed_hex"]),
        str(record["channel_symbol_count"]),
        str(record["header_codeword_hex"]),
    ]
    for _ in range(REPEATS):
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def measure(function, record: dict[str, object]) -> float:
    started = time.perf_counter()
    function(record)
    return (time.perf_counter() - started) * 1000.0 / REPEATS


def main() -> int:
    records = [
        record
        for fixture in FIXTURES
        for record in json.loads(fixture.read_text(encoding="utf-8"))["vectors"]
    ]
    print("name,python_encode_ms,native_encode_ms,encode_delta_percent,python_decode_ms,native_decode_ms,decode_delta_percent")
    for record in records:
        python_ms = measure(python_encode, record)
        native_ms = measure(native_encode, record)
        encode_delta = (native_ms / python_ms - 1.0) * 100.0
        python_decode_ms = measure(python_decode, record)
        native_decode_ms = measure(native_decode, record)
        decode_delta = (native_decode_ms / python_decode_ms - 1.0) * 100.0
        print(f"{record['name']},{python_ms:.3f},{native_ms:.3f},{encode_delta:+.1f},{python_decode_ms:.3f},{native_decode_ms:.3f},{decode_delta:+.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
