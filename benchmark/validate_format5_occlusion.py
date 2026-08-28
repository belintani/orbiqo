#!/usr/bin/env python3
"""Validate the format-5 occlusion gain across deterministic payload patterns."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from io import BytesIO

from PIL import Image

from radialcode.constants import Alphabet, EccLevel, PayloadType, QUIET_ZONE_OUTER
from radialcode.encoder import encode
from radialcode.renderer import RenderOptions, render_png_fast
from radialcode.simulation import Degradation, degrade

from run_normalized_comparison import OCCUPIED_SIZE, ORBIQO_NORMALIZED_DPI, PAYLOAD, PROFILES, OrbiqoAdapter, normalize_fixed


OUTPUT = Path(__file__).resolve().parent / "results" / "format5_occlusion_validation.json"
PAYLOADS = {
    "benchmark": PAYLOAD,
    "counter": bytes(range(len(PAYLOAD))),
    "periodic": bytes((index * 37 + 11) % 256 for index in range(len(PAYLOAD))),
}


class ProfileAdapter(OrbiqoAdapter):
    def __init__(self, level: EccLevel) -> None:
        self.level = level

    def generate_native(self, payload: bytes):  # type: ignore[no-untyped-def]
        symbol = encode(
            payload,
            payload_type=PayloadType.BINARY,
            geometry="auto",
            diameter_mm=30.0,
            alphabet=Alphabet.COLOR4,
            ecc_level=self.level,
            compression="none",
        )
        image = Image.open(
            BytesIO(render_png_fast(symbol, dpi=ORBIQO_NORMALIZED_DPI, options=RenderOptions(center_text="OQ"), supersample=2))
        ).convert("RGB")
        pitch = symbol.geometry.radial_pitch * (OCCUPIED_SIZE / (2.0 * QUIET_ZONE_OUTER))
        from run_normalized_comparison import Generated

        profile = symbol.header.ecc_level.name.lower()
        return Generated(image, OCCUPIED_SIZE / pitch, OCCUPIED_SIZE / pitch, pitch, profile, profile, profile)


def main() -> None:
    profile = PROFILES["occlusion_0_06"]
    rows: list[dict[str, object]] = []
    for level in (EccLevel.BALANCED, EccLevel.ROBUST, EccLevel.EXTREME):
        adapter = ProfileAdapter(level)
        for name, payload in PAYLOADS.items():
            generated = adapter.generate_normalized(payload)
            successes = 0
            trials: list[bool] = []
            for trial in range(4):
                seeded = Degradation(**{**asdict(profile), "seed": 101 + trial})
                decoded = adapter.decode(degrade(generated.image, seeded))
                success = decoded == payload
                trials.append(success)
                successes += int(success)
            rows.append({"ecc": level.name.lower(), "payload": name, "bytes": len(payload), "successes": successes, "trials": 4, "outcomes": trials})
    OUTPUT.write_text(json.dumps({"profile": asdict(profile), "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
