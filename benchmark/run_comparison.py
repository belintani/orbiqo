#!/usr/bin/env python3
"""Reproducible digital-only benchmark for Orbiqo, QR, Aztec, and JAB."""

from __future__ import annotations

import base64
from collections import defaultdict
import csv
from dataclasses import asdict
from io import BytesIO
from importlib.metadata import version
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
from typing import Callable

import numpy as np
from PIL import Image
import zxingcpp


ROOT = Path(__file__).resolve().parents[1]
RADIAL_ROOT = Path(os.environ.get("ORBIQO_RADIALCODE_ROOT", ROOT.parent / "radialcode")).resolve()
sys.path.insert(0, str(RADIAL_ROOT / "src"))

import radialcode
from radialcode.capacity import capacity_for
from radialcode.constants import Alphabet, EccLevel, PayloadType
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png
from radialcode.simulation import Degradation, degrade
from radialcode.vision import decode_image


RESULT_DIR = ROOT / "benchmark" / "results"
RAW_CSV = RESULT_DIR / "comparison_raw.csv"
SUMMARY_JSON = RESULT_DIR / "comparison_summary.json"
METHODOLOGY_MD = ROOT / "docs" / "BENCHMARK_METHODOLOGY.md"
PAYLOAD = bytes(((index * 73 + 19) % 256) for index in range(64))
TIMING_RUNS = 10
DEGRADATION_TRIALS = 4
CANVAS_SIZE = 1024

JAB_ROOT = ROOT / "benchmark" / "vendor" / "jabcode" / "src"
JAB_WRITER = JAB_ROOT / "jabcodeWriter" / "bin" / "jabcodeWriter"
JAB_READER = JAB_ROOT / "jabcodeReader" / "bin" / "jabcodeReader"


def normalize_canvas(image: Image.Image, size: int = CANVAS_SIZE) -> Image.Image:
    rgb = image.convert("RGB")
    inner = int(size * 0.88)
    scale = min(inner / rgb.width, inner / rgb.height)
    resized = rgb.resize((max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (size, size), "white")
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def deterministic_bytes(length: int) -> bytes:
    return bytes(((index * 131 + 29) % 256) for index in range(length))


class Adapter:
    name: str
    toolchain: str

    def generate(self, payload: bytes) -> Image.Image:
        raise NotImplementedError

    def decode(self, image: Image.Image) -> bytes | None:
        raise NotImplementedError


class OrbiqoAdapter(Adapter):
    name = "orbiqo"
    toolchain = f"radialcode {radialcode.__version__}"

    def generate(self, payload: bytes) -> Image.Image:
        symbol = encode(
            payload,
            payload_type=PayloadType.BINARY,
            geometry="auto",
            diameter_mm=30.0,
            alphabet=Alphabet.COLOR4,
            ecc_level=EccLevel.BALANCED,
            compression="none",
        )
        return Image.open(BytesIO(render_png(symbol, dpi=300, options=RenderOptions(center_text="OQ")))).convert("RGB")

    def decode(self, image: Image.Image) -> bytes | None:
        try:
            return decode_image(image, output_size=1024).decoded.payload
        except Exception:
            return None


class ZxingAdapter(Adapter):
    def __init__(self, name: str, barcode_format: zxingcpp.BarcodeFormat):
        self.name = name
        self.barcode_format = barcode_format
        self.toolchain = f"zxing-cpp {version('zxing-cpp')}"

    def generate(self, payload: bytes) -> Image.Image:
        barcode = zxingcpp.create_barcode(payload, self.barcode_format)
        array = np.asarray(zxingcpp.write_barcode_to_image(barcode, scale=8, add_quiet_zones=True))
        return Image.fromarray(array).convert("RGB")

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

    def generate(self, payload: bytes) -> Image.Image:
        with tempfile.TemporaryDirectory(prefix="orbiqo-jab-") as temp:
            temp_path = Path(temp)
            source = temp_path / "payload.bin"
            output = temp_path / "symbol.png"
            source.write_bytes(payload)
            subprocess.run(
                [
                    str(JAB_WRITER),
                    "--input-file",
                    str(source),
                    "--output",
                    str(output),
                    "--color-number",
                    "4",
                    "--module-size",
                    "8",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            return Image.open(output).convert("RGB").copy()

    def decode(self, image: Image.Image) -> bytes | None:
        with tempfile.TemporaryDirectory(prefix="orbiqo-jab-") as temp:
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


def fixed_profile_capacity(barcode_format: zxingcpp.BarcodeFormat) -> dict[str, object]:
    baseline_shape: tuple[int, ...] | None = None
    maximum = 0
    ec_level = ""
    for length in range(1, 513):
        try:
            barcode = zxingcpp.create_barcode(deterministic_bytes(length), barcode_format, version=1)
            shape = tuple(np.asarray(zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=True)).shape)
        except Exception:
            break
        if baseline_shape is None:
            baseline_shape = shape
            ec_level = barcode.ec_level
        if shape != baseline_shape:
            break
        maximum = length
    return {"maximum_payload_bytes": maximum, "raster_modules_with_quiet_zone": list(baseline_shape or ()), "ec_level": ec_level}


def jab_fixed_profile_capacity() -> dict[str, object]:
    maximum = 0
    shape: list[int] = []
    with tempfile.TemporaryDirectory(prefix="orbiqo-jab-capacity-") as temp:
        temp_path = Path(temp)
        source = temp_path / "payload.bin"
        output = temp_path / "symbol.png"
        for length in range(1, 513):
            source.write_bytes(deterministic_bytes(length))
            completed = subprocess.run(
                [
                    str(JAB_WRITER),
                    "--input-file",
                    str(source),
                    "--output",
                    str(output),
                    "--color-number",
                    "4",
                    "--module-size",
                    "1",
                    "--symbol-version",
                    "1",
                    "1",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            if completed.returncode != 0 or not output.is_file():
                break
            with Image.open(output) as image:
                current_shape = [image.width, image.height]
            if shape and current_shape != shape:
                break
            shape = current_shape
            maximum = length
    return {
        "maximum_payload_bytes": maximum,
        "raster_modules": shape,
        "ec_level": "3 (6%)",
    }


def environment() -> dict[str, object]:
    jab_commit = subprocess.run(
        ["git", "-C", str(JAB_ROOT.parent), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "generated_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "radialcode": radialcode.__version__,
        "zxing_cpp": version("zxing-cpp"),
        "pillow": version("Pillow"),
        "numpy": version("numpy"),
        "jab_commit": jab_commit,
        "payload_sha256": __import__("hashlib").sha256(PAYLOAD).hexdigest(),
        "payload_base64": base64.b64encode(PAYLOAD).decode("ascii"),
        "timing_runs": TIMING_RUNS,
        "degradation_trials": DEGRADATION_TRIALS,
        "canvas_size": CANVAS_SIZE,
        "scope": "digital generation, digital raster decode, and deterministic synthetic degradation only",
    }


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    adapters: list[Adapter] = [
        OrbiqoAdapter(),
        ZxingAdapter("qr", zxingcpp.BarcodeFormat.QRCode),
        ZxingAdapter("aztec", zxingcpp.BarcodeFormat.Aztec),
    ]
    jab_status: dict[str, object]
    try:
        jab = JabAdapter()
        smoke = jab.decode(jab.generate(b"orbiqo-jab-validation"))
        if smoke != b"orbiqo-jab-validation":
            raise RuntimeError("official JAB toolchain failed its deterministic round trip")
        adapters.append(jab)
        jab_status = {"included": True, "reason": "official writer and reader compiled and passed a deterministic round trip"}
    except Exception as exc:
        jab_status = {"included": False, "reason": str(exc)}

    rows: list[dict[str, object]] = []
    base_images: dict[str, Image.Image] = {}
    for adapter in adapters:
        generation_times = []
        for trial in range(TIMING_RUNS):
            started = perf_counter()
            generated = adapter.generate(PAYLOAD)
            generation_times.append((perf_counter() - started) * 1000.0)
            rows.append(
                {
                    "metric": "generation_time",
                    "format": adapter.name,
                    "profile": "clean",
                    "trial": trial,
                    "payload_bytes": len(PAYLOAD),
                    "success": True,
                    "time_ms": generation_times[-1],
                    "width": generated.width,
                    "height": generated.height,
                    "detail": adapter.toolchain,
                }
            )
        base = normalize_canvas(generated)
        base_images[adapter.name] = base
        for trial in range(TIMING_RUNS):
            started = perf_counter()
            decoded = adapter.decode(base)
            elapsed = (perf_counter() - started) * 1000.0
            rows.append(
                {
                    "metric": "decode_time",
                    "format": adapter.name,
                    "profile": "clean",
                    "trial": trial,
                    "payload_bytes": len(PAYLOAD),
                    "success": decoded == PAYLOAD,
                    "time_ms": elapsed,
                    "width": base.width,
                    "height": base.height,
                    "detail": adapter.toolchain,
                }
            )

        for profile_name, profile in PROFILES.items():
            for trial in range(DEGRADATION_TRIALS):
                seeded = Degradation(**{**asdict(profile), "seed": trial + 101})
                degraded = degrade(base, seeded)
                started = perf_counter()
                decoded = adapter.decode(degraded)
                elapsed = (perf_counter() - started) * 1000.0
                rows.append(
                    {
                        "metric": "degradation_decode",
                        "format": adapter.name,
                        "profile": profile_name,
                        "trial": trial,
                        "payload_bytes": len(PAYLOAD),
                        "success": decoded == PAYLOAD,
                        "time_ms": elapsed,
                        "width": degraded.width,
                        "height": degraded.height,
                        "detail": adapter.toolchain,
                    }
                )

    with RAW_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    grouped_times: dict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_success: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in rows:
        if row["metric"] in ("generation_time", "decode_time"):
            grouped_times[(str(row["format"]), str(row["metric"]))].append(float(row["time_ms"]))
        if row["metric"] == "degradation_decode":
            grouped_success[(str(row["format"]), str(row["profile"]))].append(bool(row["success"]))

    timing_summary = []
    for (format_name, metric), values in sorted(grouped_times.items()):
        timing_summary.append(
            {
                "format": format_name,
                "metric": metric,
                "runs": len(values),
                "median_ms": statistics.median(values),
                "mean_ms": statistics.fmean(values),
                "p95_ms": percentile(values, 0.95),
                "success_rate": sum(
                    bool(row["success"])
                    for row in rows
                    if row["format"] == format_name and row["metric"] == metric
                ) / len(values),
            }
        )
    degradation_summary = [
        {
            "format": format_name,
            "profile": profile,
            "successes": sum(values),
            "trials": len(values),
            "success_rate": sum(values) / len(values),
        }
        for (format_name, profile), values in sorted(grouped_success.items())
    ]
    orbiqo_capacity = capacity_for(1, Alphabet.COLOR4, EccLevel.BALANCED)
    capacity_summary = [
        {
            "format": "orbiqo",
            "profile": "small / COLOR4 / balanced",
            "maximum_payload_bytes": orbiqo_capacity.maximum_uncompressed_payload_bytes,
            "ec_level": "balanced",
            "source": "exact reference capacity model",
        },
        {"format": "qr", "profile": "version 1 / ZXing default", **fixed_profile_capacity(zxingcpp.BarcodeFormat.QRCode), "source": "largest binary payload retaining the version-1 raster size"},
        {"format": "aztec", "profile": "version 1 / ZXing default", **fixed_profile_capacity(zxingcpp.BarcodeFormat.Aztec), "source": "largest binary payload retaining the version-1 raster size"},
    ]
    if bool(jab_status.get("included")):
        capacity_summary.append(
            {
                "format": "jab",
                "profile": "single symbol / version 1×1 / COLOR4",
                **jab_fixed_profile_capacity(),
                "source": "largest binary payload accepted by the fixed official CLI profile",
            }
        )

    perspective_path = RADIAL_ROOT / "assets" / "perspective_benchmark.csv"
    perspective_rows = list(csv.DictReader(perspective_path.open(encoding="utf-8"))) if perspective_path.is_file() else []
    perspective_summary = {
        "available": bool(perspective_rows),
        "successes": sum(row.get("success") == "True" for row in perspective_rows),
        "trials": len(perspective_rows),
        "known_failures": [
            {"pose": row.get("pose"), "profile": row.get("profile"), "error": row.get("error")}
            for row in perspective_rows
            if row.get("success") != "True"
        ],
    }
    summary = {
        "schema_version": 1,
        "environment": environment(),
        "adapters": [{"format": adapter.name, "toolchain": adapter.toolchain} for adapter in adapters],
        "jab_status": jab_status,
        "capacity": capacity_summary,
        "timing": timing_summary,
        "degradation": degradation_summary,
        "orbiqo_perspective": perspective_summary,
        "limitations": [
            "All measurements are digital-only and do not support claims about printed symbols.",
            "Fixed-profile capacities are descriptive, not an ECC-equivalent comparison.",
            "JAB timing includes command-process startup; Orbiqo and ZXing run in-process.",
            "The degradation corpus is deterministic and synthetic, not a camera-device corpus.",
            "Orbiqo strong-foreshortening remains 14/16 in its separate perspective matrix.",
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Orbiqo Lab benchmark methodology",
        "",
        "> Scope: digital-only generation, digital raster decode, and deterministic synthetic degradation. No result in this suite measures or predicts print performance.",
        "",
        "The primary workload is a deterministic 64-byte binary payload. Each encoder uses its native auto-sizing behavior for timing and degradation runs, after which the output is centered on a 1024×1024 white canvas with nearest-neighbor scaling. Orbiqo runs through the RadialCode COLOR4 reference implementation, QR and Aztec run through ZXing-C++ 3.1.1, and JAB is included only after its official writer and reader complete a deterministic round trip.",
        "",
        "| Measurement | Repetitions | Definition |",
        "| --- | ---: | --- |",
        f"| Generation time | {TIMING_RUNS} | Encode plus raster generation; JAB includes CLI process startup |",
        f"| Clean decode time | {TIMING_RUNS} | End-to-end detection and payload recovery on the normalized canvas |",
        f"| Degradation success | {DEGRADATION_TRIALS} per profile | Exact byte equality after deterministic blur, noise, JPEG, downsampling, occlusion, and combined profiles |",
        "| Capacity | One deterministic sweep | Orbiqo exact model; QR/Aztec largest binary payload retaining the version-1 raster size |",
        "",
        "Raw rows are stored in `benchmark/results/comparison_raw.csv`; the dashboard consumes `benchmark/results/comparison_summary.json`. Environment versions, seeds, payload hash, parameters, and limitations are embedded in the summary.",
        "",
        "## Toolchain sources",
        "",
        "ZXing-C++ documents QR and Aztec read/write support, Python bindings, and the create/write/read APIs in its official repository.[1] The JAB repository provides the C11 writer/reader used here and identifies ISO/IEC 23634:2022 as its technical specification.[2]",
        "",
        "## References",
        "",
        "[1]: https://github.com/zxing-cpp/zxing-cpp \"ZXing-C++ official repository\"",
        "[2]: https://github.com/jabcode/jabcode \"JAB Code official repository\"",
    ]
    METHODOLOGY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(SUMMARY_JSON)
    print(RAW_CSV)


if __name__ == "__main__":
    main()
