#!/usr/bin/env python3
"""Area-normalized digital benchmark for Orbiqo, QR, Aztec, and JAB."""

from __future__ import annotations

import base64
from collections import defaultdict
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter

import numpy as np
from PIL import Image
import zxingcpp


ROOT = Path(__file__).resolve().parents[1]
RADIAL_ROOT = Path(os.environ.get("ORBIQO_RADIALCODE_ROOT", ROOT.parent / "radialcode")).resolve()
sys.path.insert(0, str(RADIAL_ROOT / "src"))

import radialcode
from radialcode.constants import Alphabet, EccLevel, PayloadType, QUIET_ZONE_OUTER
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png, render_png_fast
from radialcode.simulation import Degradation, degrade
from radialcode.vision import decode_image


RESULT_DIR = ROOT / "benchmark" / "results"
RAW_CSV = RESULT_DIR / "normalized_raw.csv"
CAPACITY_CSV = RESULT_DIR / "normalized_capacity_trials.csv"
SUMMARY_JSON = RESULT_DIR / "normalized_summary.json"
PAYLOAD = bytes(((index * 73 + 19) % 256) for index in range(64))
TIMING_RUNS = 10
DEGRADATION_TRIALS = 4
CANVAS_SIZE = 1024
OCCUPIED_SIZE = 900
ORBIQO_NORMALIZED_DPI = 725  # Produces an exact 900 px Draft 0.4 canvas before normalization.
MIN_FEATURE_PITCH_PX = 7.0
MAX_CAPACITY_SEARCH_BYTES = 8192

JAB_ROOT = Path(os.environ.get("ORBIQO_JAB_ROOT", ROOT / "benchmark" / "jabcode-runtime")).resolve()
JAB_WRITER = JAB_ROOT / "jabcodeWriter" / "bin" / "jabcodeWriter"
JAB_READER = JAB_ROOT / "jabcodeReader" / "bin" / "jabcodeReader"


PROFILES = {
    "clean": Degradation(),
    "blur_1_5": Degradation(blur_radius=1.5),
    "blur_3_0": Degradation(blur_radius=3.0),
    "noise_8": Degradation(noise_sigma=8.0),
    "jpeg_40": Degradation(jpeg_quality=40),
    "downsample_0_35": Degradation(downsample_factor=0.35),
    "occlusion_0_06": Degradation(occlusion_fraction=0.06),
    "combined": Degradation(
        blur_radius=1.2,
        noise_sigma=6.0,
        brightness=0.9,
        saturation=0.88,
        jpeg_quality=55,
        downsample_factor=0.55,
    ),
}


def deterministic_bytes(length: int) -> bytes:
    return bytes(((index * 131 + 29) % 256) for index in range(length))


def normalize_fixed(image: Image.Image) -> Image.Image:
    symbol = image.convert("RGB").resize((OCCUPIED_SIZE, OCCUPIED_SIZE), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), "white")
    offset = (CANVAS_SIZE - OCCUPIED_SIZE) // 2
    canvas.paste(symbol, (offset, offset))
    return canvas


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


@dataclass(frozen=True, slots=True)
class Generated:
    image: Image.Image
    logical_width: float
    logical_height: float
    nominal_pitch_px: float
    profile: str
    reported_ecc: str
    detail: str


class Adapter:
    name: str
    toolchain: str

    def generate_native(self, payload: bytes) -> Generated:
        raise NotImplementedError

    def decode(self, image: Image.Image) -> bytes | None:
        raise NotImplementedError

    def generate_normalized(self, payload: bytes) -> Generated:
        generated = self.generate_native(payload)
        return Generated(normalize_fixed(generated.image), generated.logical_width, generated.logical_height, generated.nominal_pitch_px, generated.profile, generated.reported_ecc, generated.detail)


class OrbiqoAdapter(Adapter):
    name = "orbiqo"
    toolchain = f"radialcode {radialcode.__version__}"

    def generate_native(self, payload: bytes) -> Generated:
        symbol = encode(
            payload,
            payload_type=PayloadType.BINARY,
            geometry="auto",
            diameter_mm=30.0,
            alphabet=Alphabet.COLOR4,
            ecc_level=EccLevel.BALANCED,
            compression="none",
        )
        image = Image.open(
            BytesIO(
                render_png_fast(
                    symbol,
                    dpi=ORBIQO_NORMALIZED_DPI,
                    options=RenderOptions(center_text="OQ"),
                    supersample=2,
                )
            )
        ).convert("RGB")
        pitch = symbol.geometry.radial_pitch * (OCCUPIED_SIZE / (2.0 * QUIET_ZONE_OUTER))
        effective_width = OCCUPIED_SIZE / pitch
        return Generated(
            image,
            effective_width,
            effective_width,
            pitch,
            f"{symbol.geometry.version.name} / COLOR4 / balanced",
            "RS(255,191), code rate 74.9%",
            f"geometry {symbol.geometry.version.number}; {symbol.geometry.version.data_rings} data rings; native raster 900 px",
        )

    def generate_capacity_normalized(self, payload: bytes) -> Generated:
        """Use the normative SVG/Cairo path for format-capacity discovery."""
        symbol = encode(
            payload,
            payload_type=PayloadType.BINARY,
            geometry="auto",
            diameter_mm=30.0,
            alphabet=Alphabet.COLOR4,
            ecc_level=EccLevel.BALANCED,
            compression="none",
        )
        image = Image.open(BytesIO(render_png(symbol, dpi=300, options=RenderOptions(center_text="OQ")))).convert("RGB")
        pitch = symbol.geometry.radial_pitch * (OCCUPIED_SIZE / (2.0 * QUIET_ZONE_OUTER))
        effective_width = OCCUPIED_SIZE / pitch
        return Generated(
            normalize_fixed(image),
            effective_width,
            effective_width,
            pitch,
            f"{symbol.geometry.version.name} / COLOR4 / balanced",
            "RS(255,191), code rate 74.9%",
            f"geometry {symbol.geometry.version.number}; normative SVG/Cairo capacity raster",
        )

    def decode(self, image: Image.Image) -> bytes | None:
        try:
            return decode_image(image, output_size=1024).decoded.payload
        except Exception:
            return None


class ZxingAdapter(Adapter):
    def __init__(self, name: str, barcode_format: zxingcpp.BarcodeFormat, requested_ecc: str):
        self.name = name
        self.barcode_format = barcode_format
        self.requested_ecc = requested_ecc
        self.toolchain = f"zxing-cpp {version('zxing-cpp')}"

    def generate_native(self, payload: bytes) -> Generated:
        barcode = zxingcpp.create_barcode(payload, self.barcode_format, ec_level=self.requested_ecc)
        matrix = np.asarray(zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=True))
        image = Image.fromarray(matrix).convert("RGB")
        logical_height, logical_width = matrix.shape[:2]
        pitch = min(OCCUPIED_SIZE / logical_width, OCCUPIED_SIZE / logical_height)
        return Generated(
            image,
            float(logical_width),
            float(logical_height),
            pitch,
            f"auto geometry / requested ECC {self.requested_ecc}",
            str(barcode.ec_level),
            f"logical raster {logical_width}×{logical_height} with quiet zone",
        )

    def decode(self, image: Image.Image) -> bytes | None:
        decoded = zxingcpp.read_barcode(image, formats=self.barcode_format)
        if decoded is None or not decoded.valid:
            return None
        return bytes(decoded.bytes)


class JabAdapter(Adapter):
    name = "jab"
    toolchain = "jabcode CLI 2.0.0 (official C11 source; -no-pie linker compatibility flag)"

    def __init__(self) -> None:
        if not JAB_WRITER.is_file() or not JAB_READER.is_file():
            raise RuntimeError("JAB writer/reader binaries are not available")

    def generate_native(self, payload: bytes) -> Generated:
        with tempfile.TemporaryDirectory(prefix="orbiqo-jab-normalized-") as temp:
            temp_path = Path(temp)
            source = temp_path / "payload.bin"
            output = temp_path / "symbol.png"
            source.write_bytes(payload)
            subprocess.run(
                [
                    str(JAB_WRITER), "--input-file", str(source), "--output", str(output),
                    "--color-number", "4", "--module-size", "1", "--ecc-level", "3",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            image = Image.open(output).convert("RGB").copy()
        pitch = min(OCCUPIED_SIZE / image.width, OCCUPIED_SIZE / image.height)
        return Generated(image, float(image.width), float(image.height), pitch, "auto geometry / COLOR4 / level 3", "level 3 (CLI: 6%)", f"logical raster {image.width}×{image.height}")

    def decode(self, image: Image.Image) -> bytes | None:
        with tempfile.TemporaryDirectory(prefix="orbiqo-jab-normalized-") as temp:
            temp_path = Path(temp)
            source = temp_path / "symbol.png"
            output = temp_path / "payload.bin"
            image.save(source, format="PNG")
            try:
                subprocess.run(
                    [str(JAB_READER), str(source), "--output", str(output)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                return None
            return output.read_bytes() if output.is_file() else None


def build_adapters() -> tuple[list[Adapter], dict[str, object]]:
    adapters: list[Adapter] = [
        OrbiqoAdapter(),
        ZxingAdapter("qr", zxingcpp.BarcodeFormat.QRCode, "Q"),
        ZxingAdapter("aztec", zxingcpp.BarcodeFormat.Aztec, "25"),
    ]
    status: dict[str, object]
    try:
        jab = JabAdapter()
        smoke = jab.decode(jab.generate_normalized(b"orbiqo-normalized-jab").image)
        if smoke != b"orbiqo-normalized-jab":
            raise RuntimeError("official JAB toolchain failed its normalized round trip")
        adapters.append(jab)
        status = {"included": True, "reason": "official writer and reader passed a normalized deterministic round trip"}
    except Exception as exc:
        status = {"included": False, "reason": str(exc)}
    return adapters, status


def capacity_attempt(adapter: Adapter, length: int) -> tuple[bool, bool, dict[str, object]]:
    payload = deterministic_bytes(length)
    try:
        generated = adapter.generate_capacity_normalized(payload) if isinstance(adapter, OrbiqoAdapter) else adapter.generate_normalized(payload)
        feature_ok = generated.nominal_pitch_px >= MIN_FEATURE_PITCH_PX
        decoded = adapter.decode(generated.image) if feature_ok else None
        exact = decoded == payload
        return feature_ok, feature_ok and exact, {
            "format": adapter.name,
            "payload_bytes": length,
            "generated": True,
            "feature_ok": feature_ok,
            "decoded_exactly": exact,
            "nominal_pitch_px": generated.nominal_pitch_px,
            "logical_width": generated.logical_width,
            "logical_height": generated.logical_height,
            "profile": generated.profile,
            "reported_ecc": generated.reported_ecc,
            "error": "",
        }
    except Exception as exc:
        return False, False, {
            "format": adapter.name,
            "payload_bytes": length,
            "generated": False,
            "feature_ok": False,
            "decoded_exactly": False,
            "nominal_pitch_px": 0.0,
            "logical_width": 0.0,
            "logical_height": 0.0,
            "profile": "",
            "reported_ecc": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def search_capacity(adapter: Adapter) -> tuple[dict[str, object], list[dict[str, object]]]:
    attempts: dict[int, tuple[bool, bool, dict[str, object]]] = {}

    def feature_valid(length: int) -> bool:
        if length not in attempts:
            attempts[length] = capacity_attempt(adapter, length)
        return attempts[length][0]

    def exact_decode(length: int) -> bool:
        if length not in attempts:
            attempts[length] = capacity_attempt(adapter, length)
        return attempts[length][1]

    low = 0
    high = 1
    while high <= MAX_CAPACITY_SEARCH_BYTES and feature_valid(high):
        low = high
        high *= 2
    high = min(high, MAX_CAPACITY_SEARCH_BYTES + 1)
    while low + 1 < high:
        midpoint = (low + high) // 2
        if feature_valid(midpoint):
            low = midpoint
        else:
            high = midpoint
    feature_ceiling = low
    exact_ceiling = feature_ceiling
    while exact_ceiling > 0 and not exact_decode(exact_ceiling):
        exact_ceiling -= 1
    if exact_ceiling == 0:
        raise RuntimeError(f"{adapter.name} could not encode one byte under normalized constraints")
    _, _, best = attempts[exact_ceiling]
    summary = {
        "format": adapter.name,
        "maximum_payload_bytes": exact_ceiling,
        "feature_valid_payload_ceiling_bytes": feature_ceiling,
        "clean_decode_gap_bytes": feature_ceiling - exact_ceiling,
        "nominal_pitch_px": best["nominal_pitch_px"],
        "logical_width": best["logical_width"],
        "logical_height": best["logical_height"],
        "profile": best["profile"],
        "reported_ecc": best["reported_ecc"],
        "bytes_per_100k_occupied_px": low / (OCCUPIED_SIZE * OCCUPIED_SIZE) * 100_000.0,
        "constraint": f"exact clean decode and nominal pitch ≥ {MIN_FEATURE_PITCH_PX:.1f}px",
    }
    return summary, [attempts[length][2] for length in sorted(attempts)]


def environment() -> dict[str, object]:
    jab_commit = subprocess.run(["git", "-C", str(JAB_ROOT.parent), "rev-parse", "HEAD"], check=False, capture_output=True, text=True).stdout.strip()
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "radialcode": radialcode.__version__,
        "zxing_cpp": version("zxing-cpp"),
        "pillow": version("Pillow"),
        "numpy": version("numpy"),
        "jab_commit": jab_commit,
        "payload_sha256": sha256(PAYLOAD).hexdigest(),
        "payload_base64": base64.b64encode(PAYLOAD).decode("ascii"),
        "timing_runs": TIMING_RUNS,
        "degradation_trials": DEGRADATION_TRIALS,
        "canvas_size": CANVAS_SIZE,
        "occupied_size": OCCUPIED_SIZE,
        "minimum_feature_pitch_px": MIN_FEATURE_PITCH_PX,
        "scope": "digital-only normalized generation, raster decode, and deterministic synthetic degradation",
    }


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    adapters, jab_status = build_adapters()
    rows: list[dict[str, object]] = []
    base_images: dict[str, Image.Image] = {}
    adapter_profiles: list[dict[str, object]] = []

    for adapter in adapters:
        generated = adapter.generate_normalized(PAYLOAD)
        if generated.image.size != (CANVAS_SIZE, CANVAS_SIZE):
            raise AssertionError("normalized image dimensions drifted")
        if adapter.decode(generated.image) != PAYLOAD:
            raise AssertionError(f"{adapter.name} failed the normalized clean round trip")
        adapter_profiles.append(
            {
                "format": adapter.name,
                "toolchain": adapter.toolchain,
                "profile": generated.profile,
                "reported_ecc": generated.reported_ecc,
                "logical_width": generated.logical_width,
                "logical_height": generated.logical_height,
                "nominal_pitch_px": generated.nominal_pitch_px,
            }
        )

        for trial in range(TIMING_RUNS):
            started = perf_counter()
            timed_generated = adapter.generate_normalized(PAYLOAD)
            elapsed = (perf_counter() - started) * 1000.0
            rows.append(
                {
                    "metric": "generation_time", "format": adapter.name, "profile": "normalized_clean", "trial": trial,
                    "payload_bytes": len(PAYLOAD), "success": True, "time_ms": elapsed,
                    "width": timed_generated.image.width, "height": timed_generated.image.height,
                    "occupied_width": OCCUPIED_SIZE, "occupied_height": OCCUPIED_SIZE,
                    "nominal_pitch_px": timed_generated.nominal_pitch_px, "reported_ecc": timed_generated.reported_ecc,
                    "detail": adapter.toolchain,
                }
            )
        base_images[adapter.name] = generated.image
        for trial in range(TIMING_RUNS):
            started = perf_counter()
            decoded = adapter.decode(generated.image)
            elapsed = (perf_counter() - started) * 1000.0
            rows.append(
                {
                    "metric": "decode_time", "format": adapter.name, "profile": "normalized_clean", "trial": trial,
                    "payload_bytes": len(PAYLOAD), "success": decoded == PAYLOAD, "time_ms": elapsed,
                    "width": generated.image.width, "height": generated.image.height,
                    "occupied_width": OCCUPIED_SIZE, "occupied_height": OCCUPIED_SIZE,
                    "nominal_pitch_px": generated.nominal_pitch_px, "reported_ecc": generated.reported_ecc,
                    "detail": adapter.toolchain,
                }
            )

        for profile_name, profile in PROFILES.items():
            for trial in range(DEGRADATION_TRIALS):
                seeded = Degradation(**{**asdict(profile), "seed": trial + 101})
                degraded = degrade(generated.image, seeded)
                started = perf_counter()
                decoded = adapter.decode(degraded)
                elapsed = (perf_counter() - started) * 1000.0
                rows.append(
                    {
                        "metric": "degradation_decode", "format": adapter.name, "profile": profile_name, "trial": trial,
                        "payload_bytes": len(PAYLOAD), "success": decoded == PAYLOAD, "time_ms": elapsed,
                        "width": degraded.width, "height": degraded.height,
                        "occupied_width": OCCUPIED_SIZE, "occupied_height": OCCUPIED_SIZE,
                        "nominal_pitch_px": generated.nominal_pitch_px, "reported_ecc": generated.reported_ecc,
                        "detail": adapter.toolchain,
                    }
                )

    with RAW_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    capacity_summary: list[dict[str, object]] = []
    capacity_rows: list[dict[str, object]] = []
    for adapter in adapters:
        summary, attempts = search_capacity(adapter)
        capacity_summary.append(summary)
        capacity_rows.extend(attempts)
    with CAPACITY_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(capacity_rows[0]))
        writer.writeheader()
        writer.writerows(capacity_rows)

    grouped_times: dict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_success: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in rows:
        if row["metric"] in ("generation_time", "decode_time"):
            grouped_times[(str(row["format"]), str(row["metric"]))].append(float(row["time_ms"]))
        if row["metric"] == "degradation_decode":
            grouped_success[(str(row["format"]), str(row["profile"]))].append(bool(row["success"]))
    timing_summary = [
        {
            "format": format_name, "metric": metric, "runs": len(values),
            "median_ms": statistics.median(values), "mean_ms": statistics.fmean(values),
            "p95_ms": percentile(values, 0.95),
            "success_rate": sum(bool(row["success"]) for row in rows if row["format"] == format_name and row["metric"] == metric) / len(values),
        }
        for (format_name, metric), values in sorted(grouped_times.items())
    ]
    degradation_summary = [
        {"format": format_name, "profile": profile, "successes": sum(values), "trials": len(values), "success_rate": sum(values) / len(values)}
        for (format_name, profile), values in sorted(grouped_success.items())
    ]
    summary = {
        "schema_version": 1,
        "normalization": {
            "canvas_size": CANVAS_SIZE,
            "occupied_size": OCCUPIED_SIZE,
            "minimum_feature_pitch_px": MIN_FEATURE_PITCH_PX,
            "timing_payload_bytes": len(PAYLOAD),
            "timing_payload_sha256": sha256(PAYLOAD).hexdigest(),
            "success_criterion": "exact byte equality",
            "orbiqo_capacity_renderer": "normative SVG/Cairo raster",
            "orbiqo_product_renderer": "direct Pillow raster at 725 DPI and supersample 2",
        },
        "environment": environment(),
        "adapters": adapter_profiles,
        "jab_status": jab_status,
        "capacity": capacity_summary,
        "timing": timing_summary,
        "degradation": degradation_summary,
        "limitations": [
            "All measurements are digital-only and do not support claims about printed symbols.",
            "Equal outer area and nominal feature pitch do not make finder overhead, cell shape, color classification, or ECC families equivalent.",
            "QR uses Q; Aztec stores the writer-reported ECC; Orbiqo uses Balanced RS; JAB uses official CLI level 3. No overall ECC winner is claimed.",
            "JAB timing includes command-process startup; Orbiqo and ZXing run in-process.",
            "Orbiqo capacity uses its normative SVG/Cairo raster; timing and degradation use the optimized direct PNG renderer shipped in the lab.",
            "The degradation corpus is deterministic and synthetic, not a camera-device corpus.",
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(SUMMARY_JSON)
    print(RAW_CSV)
    print(CAPACITY_CSV)


if __name__ == "__main__":
    main()
