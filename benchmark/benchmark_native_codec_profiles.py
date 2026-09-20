#!/usr/bin/env python3
"""Measure logical Python versus C++ codec performance by ECC and geometry.

This benchmark is intentionally in-process for each implementation: Python runs
in the current interpreter and C++ runs in one benchmark process per vector.
PNG, SVG, image decoding and vision are excluded. Unsupported protocol
combinations are recorded rather than silently omitted.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "benchmark"
sys.path.insert(0, str(BENCHMARK_DIR))
sys.path.insert(0, str(ROOT / "server/python/vendor/radialcode/src"))

import benchmark_native_codec_inprocess as base  # noqa: E402
from generate_native_codec_vectors import case_record  # noqa: E402
from radialcode.constants import Alphabet, EccLevel, PayloadType  # noqa: E402
from radialcode.capacity import capacity_for  # noqa: E402
from radialcode.constants import GEOMETRY_VERSIONS  # noqa: E402

REPEATS = 500
OUTPUT_CSV = ROOT / "benchmark/results/native_codec_profiles_comparison.csv"
OUTPUT_JSON = ROOT / "benchmark/results/native_codec_profiles_summary.json"


def payload_for(length: int) -> bytes:
    return bytes((index * 73 + 19) % 256 for index in range(length))


def build_record(geometry: int, ecc: EccLevel) -> tuple[dict[str, object] | None, int, str | None]:
    capacity = capacity_for(geometry, Alphabet.COLOR4, ecc, format_version=5)
    target = max(1, min(capacity.maximum_uncompressed_payload_bytes, 256))
    last_error: str | None = None
    while target > 0:
        try:
            record = case_record(
                f"profile_format5_{GEOMETRY_VERSIONS[geometry].name}_{ecc.name.lower()}",
                5,
                geometry,
                payload_for(target),
                PayloadType.BINARY,
                ecc,
                "none",
            )
            return record, capacity.maximum_uncompressed_payload_bytes, None
        except (ValueError, IndexError) as error:
            last_error = str(error)
            target -= 1
    return None, capacity.maximum_uncompressed_payload_bytes, last_error


def main() -> int:
    base.REPEATS = REPEATS
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for geometry in sorted(GEOMETRY_VERSIONS):
        for ecc in EccLevel:
            record, capacity, error = build_record(geometry, ecc)
            geometry_name = GEOMETRY_VERSIONS[geometry].name
            if record is None:
                rows.append({
                    "status": "unsupported",
                    "geometry": geometry,
                    "geometry_name": geometry_name,
                    "ecc": ecc.name,
                    "capacity_bytes": capacity,
                    "error": error or "no valid payload",
                })
                continue
            python_encode_ms = base.python_mean_ms(base.python_encode_once, record)
            python_decode_ms = base.python_mean_ms(base.python_decode_once, record)
            native = base.native_mean(record)
            cpp_encode_ms = native["encode_mean_ms"]
            cpp_decode_ms = native["decode_mean_ms"]
            rows.append({
                "status": "measured",
                "geometry": geometry,
                "geometry_name": geometry_name,
                "ecc": ecc.name,
                "payload_bytes": len(bytes.fromhex(str(record["payload_hex"]))),
                "capacity_bytes": capacity,
                "python_encode_ms": round(python_encode_ms, 6),
                "cpp_encode_ms": round(cpp_encode_ms, 6),
                "encode_delta_percent": round((cpp_encode_ms / python_encode_ms - 1.0) * 100.0, 3),
                "python_decode_ms": round(python_decode_ms, 6),
                "cpp_decode_ms": round(cpp_decode_ms, 6),
                "decode_delta_percent": round((cpp_decode_ms / python_decode_ms - 1.0) * 100.0, 3),
                "repeats": REPEATS,
            })
    fields = sorted({key for row in rows for key in row})
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    measured = [row for row in rows if row["status"] == "measured"]
    summary = {
        "schema_version": 1,
        "scope": "logical codec only; in-process Python and C++ benchmark; no PNG, SVG or vision",
        "repeats": REPEATS,
        "total_combinations": len(rows),
        "measured_combinations": len(measured),
        "unsupported_combinations": len(rows) - len(measured),
        "encode_delta_median_percent": sorted(row["encode_delta_percent"] for row in measured)[len(measured) // 2] if measured else None,
        "decode_delta_median_percent": sorted(row["decode_delta_percent"] for row in measured)[len(measured) // 2] if measured else None,
        "rows": rows,
    }
    OUTPUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
