#!/usr/bin/env python3
"""Measure normalized 6% occlusion recovery for each Orbiqo ECC profile."""

from __future__ import annotations

import os
from dataclasses import asdict
from io import BytesIO
from math import sqrt

import numpy as np

os.environ.setdefault("ORBIQO_RADIALCODE_ROOT", "/home/ubuntu/radialcode")

from run_normalized_comparison import OCCUPIED_SIZE, PAYLOAD, PROFILES, normalize_fixed  # noqa: E402
from PIL import Image  # noqa: E402
from radialcode.constants import Alphabet, EccLevel, PayloadType  # noqa: E402
from radialcode.encoder import encode  # noqa: E402
from radialcode.renderer import RenderOptions, render_png_fast  # noqa: E402
from radialcode.simulation import Degradation, degrade  # noqa: E402
from radialcode.vision import decode_image  # noqa: E402


def main() -> None:
    profile = PROFILES["occlusion_0_06"]
    for trial in range(4):
        rng = np.random.default_rng((trial + 101) ^ 0x5A17)
        side = int(round(sqrt(1024 * 1024 * profile.occlusion_fraction)))
        center_x = int(round(1024 * float(rng.uniform(0.28, 0.72))))
        center_y = int(round(1024 * float(rng.uniform(0.28, 0.72))))
        fill = "white" if int(rng.integers(0, 2)) else "black"
        print({"seed": trial + 101, "fill": fill, "box": (center_x - side // 2, center_y - side // 2, center_x + side // 2, center_y + side // 2)})
    for ecc in EccLevel:
        symbol = encode(
            PAYLOAD,
            payload_type=PayloadType.BINARY,
            geometry="auto",
            diameter_mm=30.0,
            alphabet=Alphabet.COLOR4,
            ecc_level=ecc,
            compression="none",
        )
        native = Image.open(BytesIO(render_png_fast(symbol, dpi=725, options=RenderOptions(center_text="OQ"), supersample=2))).convert("RGB")
        image = normalize_fixed(native)
        trials = []
        for trial in range(4):
            degraded = degrade(image, Degradation(**{**asdict(profile), "seed": trial + 101}))
            try:
                decoded = decode_image(degraded).decoded.payload
                trials.append(decoded == PAYLOAD)
            except Exception:
                trials.append(False)
        print({"ecc": ecc.name.lower(), "geometry": symbol.geometry.version.name, "frame_bytes": symbol.header.encoded_payload_length, "successes": sum(trials), "trials": len(trials), "results": trials})


if __name__ == "__main__":
    main()
