"""Compare practical Orbiqo ECC profiles before any external-format benchmark.

The benchmark deliberately measures the profiles as product configurations: every
profile receives the same 64-byte input and may select its smallest compatible
geometry through ``geometry='auto'``. It reports the selected geometry so this is
not confused with a fixed-geometry coding-theory comparison.
"""

from __future__ import annotations

import base64
import csv
import json
import platform
import statistics
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter

from PIL import Image

from radialcode import __version__ as radialcode_version
from radialcode.constants import Alphabet, EccLevel, PayloadType, QUIET_ZONE_OUTER
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png_fast
from radialcode.simulation import Degradation, degrade

from run_normalized_comparison import OCCUPIED_SIZE, ORBIQO_NORMALIZED_DPI, normalize_fixed
from validate_format5_occlusion import PAYLOADS, ProfileAdapter


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmark" / "results"
SUMMARY_PATH = RESULTS / "ecc_profile_comparison.json"
RAW_PATH = RESULTS / "ecc_profile_comparison_raw.csv"
PAYLOAD = PAYLOADS["benchmark"]
TIMING_RUNS = 10
OCCLUSION_TRIALS = 4
OCCLUSION_PROFILE = Degradation(occlusion_fraction=0.06)
LEVELS = (EccLevel.FAST, EccLevel.BALANCED, EccLevel.ROBUST, EccLevel.EXTREME)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) * fraction) + 0.999999) - 1))
    return float(ordered[index])


def encode_symbol(level: EccLevel, payload: bytes):  # type: ignore[no-untyped-def]
    return encode(
        payload,
        payload_type=PayloadType.BINARY,
        geometry="auto",
        diameter_mm=30.0,
        alphabet=Alphabet.COLOR4,
        ecc_level=level,
        compression="none",
    )


def render_normalized(symbol) -> Image.Image:  # type: ignore[no-untyped-def]
    image = Image.open(
        BytesIO(render_png_fast(symbol, dpi=ORBIQO_NORMALIZED_DPI, options=RenderOptions(center_text="OQ"), supersample=2))
    ).convert("RGB")
    return normalize_fixed(image)


def timing_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "runs": len(values),
        "median_ms": statistics.median(values),
        "mean_ms": statistics.fmean(values),
        "p95_ms": percentile(values, 0.95),
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    raw_rows: list[dict[str, object]] = []
    profiles: list[dict[str, object]] = []

    for level in LEVELS:
        profile_name = level.name.lower()
        adapter = ProfileAdapter(level)
        sample = encode_symbol(level, PAYLOAD)
        image = render_normalized(sample)
        clean = adapter.decode(image)
        if clean != PAYLOAD:
            raise AssertionError(f"{profile_name} failed its normalized clean round trip")

        encode_times: list[float] = []
        for trial in range(TIMING_RUNS):
            started = perf_counter()
            encoded = encode_symbol(level, PAYLOAD)
            elapsed = (perf_counter() - started) * 1000.0
            encode_times.append(elapsed)
            raw_rows.append({
                "metric": "encode_time", "ecc": profile_name, "trial": trial, "payload": "benchmark",
                "payload_bytes": len(PAYLOAD), "time_ms": elapsed, "success": True,
                "geometry": encoded.geometry.version.name.lower(), "data_rings": encoded.geometry.version.data_rings,
            })

        decode_times: list[float] = []
        for trial in range(TIMING_RUNS):
            started = perf_counter()
            decoded = adapter.decode(image)
            elapsed = (perf_counter() - started) * 1000.0
            decode_times.append(elapsed)
            raw_rows.append({
                "metric": "decode_time", "ecc": profile_name, "trial": trial, "payload": "benchmark",
                "payload_bytes": len(PAYLOAD), "time_ms": elapsed, "success": decoded == PAYLOAD,
                "geometry": sample.geometry.version.name.lower(), "data_rings": sample.geometry.version.data_rings,
            })

        occlusion_rows: list[dict[str, object]] = []
        for payload_name, payload in PAYLOADS.items():
            generated = adapter.generate_normalized(payload)
            outcomes: list[bool] = []
            for trial in range(OCCLUSION_TRIALS):
                seeded = Degradation(**{**asdict(OCCLUSION_PROFILE), "seed": 101 + trial})
                success = adapter.decode(degrade(generated.image, seeded)) == payload
                outcomes.append(success)
                raw_rows.append({
                    "metric": "occlusion", "ecc": profile_name, "trial": trial, "payload": payload_name,
                    "payload_bytes": len(payload), "time_ms": "", "success": success,
                    "geometry": generated.profile.split(" /")[0], "data_rings": "",
                })
            occlusion_rows.append({
                "payload": payload_name,
                "bytes": len(payload),
                "successes": sum(outcomes),
                "trials": OCCLUSION_TRIALS,
                "outcomes": outcomes,
            })

        pitch = sample.geometry.radial_pitch * (OCCUPIED_SIZE / (2.0 * QUIET_ZONE_OUTER))
        profiles.append({
            "ecc": profile_name,
            "geometry": sample.geometry.version.name.lower(),
            "geometry_version": sample.geometry.version.number,
            "data_rings": sample.geometry.version.data_rings,
            "diameter_mm": sample.diameter_mm,
            "nominal_pitch_px": pitch,
            "code": sample.header.ecc_level.name.lower(),
            "encode": timing_summary(encode_times),
            "decode": timing_summary(decode_times),
            "occlusion": {
                "minimum_successes": min(int(row["successes"]) for row in occlusion_rows),
                "trials_per_pattern": OCCLUSION_TRIALS,
                "rows": occlusion_rows,
            },
        })

    with RAW_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw_rows[0]))
        writer.writeheader()
        writer.writerows(raw_rows)

    summary = {
        "schema_version": 1,
        "environment": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "radialcode": radialcode_version,
        },
        "method": {
            "scope": "digital-only internal ECC-profile comparison",
            "payload_bytes": len(PAYLOAD),
            "payload_sha256": sha256(PAYLOAD).hexdigest(),
            "payload_base64": base64.b64encode(PAYLOAD).decode("ascii"),
            "geometry_selection": "auto selects the smallest compatible Orbiqo geometry independently for each profile",
            "encode_measurement": "encode() framing, ECC and placement only; direct PNG rendering is excluded",
            "decode_measurement": "full decode from the same normalized 1024 px digital raster, including vision",
            "timing_runs": TIMING_RUNS,
            "occlusion": {
                "fraction": OCCLUSION_PROFILE.occlusion_fraction,
                "payload_patterns": list(PAYLOADS),
                "trials_per_pattern": OCCLUSION_TRIALS,
                "seeds": list(range(101, 101 + OCCLUSION_TRIALS)),
                "success_criterion": "exact byte equality",
            },
        },
        "profiles": profiles,
        "limitations": [
            "This compares practical auto-selected Orbiqo profile configurations, not a fixed-geometry coding-theory experiment.",
            "Timings are reference-implementation timings on one machine and should not be read as device guarantees.",
            "The occlusion corpus is digital and synthetic; it does not validate print, camera, logo, or arbitrary-overlay behavior.",
            "More parity is not assumed to be monotonic; every profile is reported from the measured corpus.",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(SUMMARY_PATH)
    print(RAW_PATH)


if __name__ == "__main__":
    main()
