"""Build a transparent before/after artifact from the frozen baseline and current summary."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "benchmark" / "baselines" / "pre_optimization_normalized.json"
SUMMARY_PATH = ROOT / "benchmark" / "results" / "normalized_summary.json"
OUTPUT_PATH = ROOT / "benchmark" / "results" / "optimization_delta.json"


def percent_change(before: float, after: float) -> float:
    return (after - before) / before * 100.0


def main() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    capacity = next(row for row in summary["capacity"] if row["format"] == "orbiqo")["maximum_payload_bytes"]
    generation = next(row for row in summary["timing"] if row["format"] == "orbiqo" and row["metric"] == "generation_time")["median_ms"]
    decode = next(row for row in summary["timing"] if row["format"] == "orbiqo" and row["metric"] == "decode_time")["median_ms"]
    all_successes = sum(row["successes"] for row in summary["degradation"])
    all_trials = sum(row["trials"] for row in summary["degradation"])
    orbiqo_rows = [row for row in summary["degradation"] if row["format"] == "orbiqo"]
    orbiqo_successes = sum(row["successes"] for row in orbiqo_rows)
    orbiqo_trials = sum(row["trials"] for row in orbiqo_rows)

    output = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_path": str(BASELINE_PATH.relative_to(ROOT)),
        "current_summary_path": str(SUMMARY_PATH.relative_to(ROOT)),
        "methodology": baseline["methodology"],
        "metrics": [
            {
                "key": "capacity",
                "label": "Orbiqo capacity",
                "before": baseline["orbiqo_capacity_bytes"],
                "after": capacity,
                "unit": "B",
                "change": capacity - baseline["orbiqo_capacity_bytes"],
                "change_percent": percent_change(baseline["orbiqo_capacity_bytes"], capacity),
                "direction": "higher_is_better",
            },
            {
                "key": "generation",
                "label": "Median generation",
                "before": baseline["orbiqo_generation_median_ms"],
                "after": generation,
                "unit": "ms",
                "change": generation - baseline["orbiqo_generation_median_ms"],
                "change_percent": percent_change(baseline["orbiqo_generation_median_ms"], generation),
                "direction": "lower_is_better",
            },
            {
                "key": "decode",
                "label": "Median decode",
                "before": baseline["orbiqo_decode_median_ms"],
                "after": decode,
                "unit": "ms",
                "change": decode - baseline["orbiqo_decode_median_ms"],
                "change_percent": percent_change(baseline["orbiqo_decode_median_ms"], decode),
                "direction": "lower_is_better",
            },
            {
                "key": "robustness",
                "label": "All-format exact degradation",
                "before": baseline["all_formats_degradation_successes"] / baseline["all_formats_degradation_trials"] * 100.0,
                "after": all_successes / all_trials * 100.0,
                "unit": "%",
                "change": (all_successes / all_trials - baseline["all_formats_degradation_successes"] / baseline["all_formats_degradation_trials"]) * 100.0,
                "change_percent": percent_change(
                    baseline["all_formats_degradation_successes"] / baseline["all_formats_degradation_trials"] * 100.0,
                    all_successes / all_trials * 100.0,
                ),
                "direction": "higher_is_better",
            },
        ],
        "orbiqo_degradation": {
            "before": baseline["orbiqo_degradation_successes"],
            "after": orbiqo_successes,
            "trials": orbiqo_trials,
        },
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
