#!/usr/bin/env python3
"""Diagnose the normalized occlusion profile through Orbiqo's vision and canonical paths."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("ORBIQO_RADIALCODE_ROOT", "/home/ubuntu/radialcode")

from run_normalized_comparison import (  # noqa: E402
    PAYLOAD,
    PROFILES,
    OrbiqoAdapter,
)
from radialcode.decoder import decode_canonical  # noqa: E402
from radialcode.simulation import Degradation, degrade  # noqa: E402
from radialcode.vision import _dark_extent_guard_candidate, _frontal_rectification, _load_bgr, decode_image  # noqa: E402


OUTPUT = Path(__file__).resolve().parent / "results" / "orbiqo_occlusion_diagnostics.json"


def decode_result(label: str, func) -> dict[str, object]:  # type: ignore[no-untyped-def]
    try:
        decoded = func()
        return {
            "path": label,
            "success": decoded.payload == PAYLOAD,
            "geometry": decoded.header.geometry_version,
            "header_corrections": list(decoded.diagnostics.header_corrected_bits),
            "rs_corrections": decoded.diagnostics.corrected_rs_symbols,
            "erasure_bytes": decoded.diagnostics.erasure_bytes,
        }
    except Exception as error:  # Diagnostics must retain explicit failures.
        return {"path": label, "success": False, "error": f"{type(error).__name__}: {error}"}


def main() -> None:
    adapter = OrbiqoAdapter()
    generated = adapter.generate_normalized(PAYLOAD)
    rows: list[dict[str, object]] = []
    profile = PROFILES["occlusion_0_06"]
    for trial in range(4):
        seeded = Degradation(**{**asdict(profile), "seed": trial + 101})
        image = degrade(generated.image, seeded)
        bgr = _load_bgr(image)
        row = {
            "trial": trial,
            "seed": seeded.seed,
            "vision": decode_result("vision", lambda: decode_image(image, output_size=1024).decoded),
            "canonical": decode_result("canonical", lambda: decode_canonical(image)),
            "dark_extent": decode_result(
                "dark_extent",
                lambda: decode_canonical(_frontal_rectification(bgr, _dark_extent_guard_candidate(bgr), 1024).image),
            ),
        }
        rows.append(row)
        print(json.dumps(row, sort_keys=True))
    OUTPUT.write_text(json.dumps({"profile": asdict(profile), "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
