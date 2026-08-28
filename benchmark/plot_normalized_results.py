#!/usr/bin/env python3
"""Render the normalized benchmark summary as a publication-ready chart."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "benchmark" / "results" / "normalized_summary.json"
OUTPUT = ROOT / "benchmark" / "results" / "normalized_results.png"
ORDER = ["orbiqo", "qr", "aztec", "jab"]
LABELS = {"orbiqo": "Orbiqo", "qr": "QR", "aztec": "Aztec", "jab": "JAB"}
COLORS = {"orbiqo": "#ef5b3f", "qr": "#202430", "aztec": "#25aeb8", "jab": "#7569d8"}


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    capacity = {row["format"]: row for row in summary["capacity"]}
    timing = {(row["format"], row["metric"]): row for row in summary["timing"]}

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titleweight": "bold", "axes.titlesize": 13})
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=180)
    figure.patch.set_facecolor("#f4f0e8")
    for axis in axes:
        axis.set_facecolor("#fbf8f1")
        axis.spines[["top", "right", "left"]].set_visible(False)

    names = [LABELS[name] for name in ORDER]
    values = [capacity[name]["maximum_payload_bytes"] for name in ORDER]
    bars = axes[0].bar(names, values, color=[COLORS[name] for name in ORDER], width=0.64)
    axes[0].set_title("Capacity at equal 900×900 px area and ≥7 px pitch", loc="left")
    axes[0].set_ylabel("Maximum exact-decode payload (bytes)")
    axes[0].bar_label(bars, padding=4, fontsize=9, fontweight="bold")

    positions = np.arange(len(ORDER))
    generation = [timing[(name, "generation_time")]["median_ms"] for name in ORDER]
    decoding = [timing[(name, "decode_time")]["median_ms"] for name in ORDER]
    axes[1].barh(positions - 0.16, generation, height=0.28, color="#ef5b3f", label="Generation")
    axes[1].barh(positions + 0.16, decoding, height=0.28, color="#25aeb8", label="Decode")
    axes[1].set_yticks(positions, names)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Median runtime (ms, logarithmic scale)")
    axes[1].set_title("Current implementation latency", loc="left")
    axes[1].legend(frameon=False, loc="lower right")
    axes[1].invert_yaxis()

    figure.suptitle("Orbiqo normalized digital benchmark", x=0.06, ha="left", fontsize=17, fontweight="bold")
    figure.text(0.06, 0.01, "Digital-only. ECC families and implementation languages differ; no overall winner claim.", fontsize=8, color="#666970")
    figure.tight_layout(rect=(0.03, 0.05, 0.99, 0.91))
    figure.savefig(OUTPUT, facecolor=figure.get_facecolor(), bbox_inches="tight")
    print(OUTPUT)


if __name__ == "__main__":
    main()
