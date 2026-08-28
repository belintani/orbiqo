#!/usr/bin/env python3
"""Inspect per-ring BCH corruption under the normalized 6% occlusion profile."""

from __future__ import annotations

import os
from dataclasses import asdict

os.environ.setdefault("ORBIQO_RADIALCODE_ROOT", "/home/ubuntu/radialcode")

from run_normalized_comparison import PAYLOAD, PROFILES, OrbiqoAdapter  # noqa: E402
from radialcode.bootstrap import HEADER_SLOT_OFFSETS, header_codeword_from_physical, header_codeword_majority_from_physical, header_physical_bits  # noqa: E402
from radialcode.decoder import DecodeError, _load_rgb, _sample_header_ring, decode_canonical  # noqa: E402
from radialcode.header import RadialHeader  # noqa: E402
from radialcode.simulation import Degradation, degrade  # noqa: E402
from radialcode.vision import _detect_outer_guard_bgr, _frontal_rectification, _load_bgr  # noqa: E402


def hamming(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    return sum(first != second for first, second in zip(left, right, strict=True))


def main() -> None:
    adapter = OrbiqoAdapter()
    generated = adapter.generate_normalized(PAYLOAD)
    # Recreate the same header via canonical generation path.
    from radialcode.constants import Alphabet, EccLevel, PayloadType
    from radialcode.encoder import encode

    symbol = encode(PAYLOAD, payload_type=PayloadType.BINARY, geometry="auto", diameter_mm=30.0, alphabet=Alphabet.COLOR4, ecc_level=EccLevel.BALANCED, compression="none")
    expected = tuple(header_physical_bits(symbol.header, index) for index in range(3))
    profile = PROFILES["occlusion_0_06"]
    cases = [("clean", generated.image)] + [
        (f"occlusion_seed_{trial + 101}", degrade(generated.image, Degradation(**{**asdict(profile), "seed": trial + 101})))
        for trial in range(4)
    ]
    for label, image in cases:
        bgr = _load_bgr(image)
        guard = _detect_outer_guard_bgr(bgr)
        rectified = _frontal_rectification(bgr, guard, 1024)
        array = _load_rgb(rectified.image)
        observed: list[tuple[int, ...] | None] = []
        for index in range(3):
            try:
                observed.append(_sample_header_ring(array, index))
            except DecodeError:
                observed.append(None)
        per_ring = []
        for index in range(3):
            bits = observed[index]
            if bits is None:
                per_ring.append({"ring": index, "sample": "threshold-failed"})
                continue
            codeword = header_codeword_from_physical(bits, index)
            try:
                _, corrected = RadialHeader.decode_codeword(codeword)
                decoded = f"ok:{corrected}"
            except Exception as error:
                decoded = type(error).__name__
            per_ring.append({"ring": index, "physical_errors": hamming(expected[index], observed[index]), "decode": decoded})
        if all(bits is not None for bits in observed):
            try:
                copies = tuple(bits for bits in observed if bits is not None)
                logical = [
                    [copies[copy_index][(HEADER_SLOT_OFFSETS[copy_index] + 1 + bit_index) % 64] for bit_index in range(63)]
                    for copy_index in range(3)
                ]
                expected_code = symbol.header.codeword_bits()
                majority_bits = tuple(1 if sum(logical[copy_index][bit_index] for copy_index in range(3)) >= 2 else 0 for bit_index in range(63))
                disagreement = sum(len({logical[copy_index][bit_index] for copy_index in range(3)}) > 1 for bit_index in range(63))
                majority_errors = hamming(expected_code, majority_bits)
                _, corrected = RadialHeader.decode_codeword(header_codeword_majority_from_physical(copies))
                majority = f"ok:{corrected}; disagreements={disagreement}; errors={majority_errors}"
            except Exception as error:
                majority = f"{type(error).__name__}; disagreements={disagreement}; errors={majority_errors}"
        else:
            majority = "unavailable"
        try:
            decoded = decode_canonical(rectified.image)
            payload = {
                "canonical": "ok",
                "payload_matches": decoded.payload == PAYLOAD,
                "rs_corrections": decoded.diagnostics.corrected_rs_symbols,
                "erasure_bytes": decoded.diagnostics.erasure_bytes,
            }
        except Exception as error:
            payload = {"canonical": f"{type(error).__name__}: {error}"}
        print({"case": label, "per_ring": per_ring, "majority": majority, **payload})


if __name__ == "__main__":
    main()
