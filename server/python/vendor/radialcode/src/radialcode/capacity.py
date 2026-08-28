"""Exact nominal capacity calculations across RadialCode format versions."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import FORMAT_VERSION, GEOMETRY_SELECTION_ORDER, GEOMETRY_VERSIONS, Alphabet, EccLevel
from .ecc import encoded_length, maximum_payload_for_encoded_capacity
from .framing import FRAME_FIXED_OVERHEAD
from .geometry import geometry_for_format


@dataclass(frozen=True, slots=True)
class Capacity:
    format_version: int
    geometry_version: int
    alphabet: Alphabet
    ecc_level: EccLevel
    payload_cells: int
    channel_bits: int
    channel_bytes: int
    maximum_frame_bytes: int
    maximum_uncompressed_payload_bytes: int



def capacity_for(
    geometry_version: int,
    alphabet: Alphabet = Alphabet.COLOR4,
    ecc_level: EccLevel = EccLevel.BALANCED,
    *,
    format_version: int = FORMAT_VERSION,
) -> Capacity:
    geometry = geometry_for_format(geometry_version, format_version)
    payload_cells = len(geometry.payload_addresses(alphabet))
    channel_bits = payload_cells * alphabet.bits_per_cell
    channel_bytes = channel_bits // 8
    maximum_frame = maximum_payload_for_encoded_capacity(channel_bytes, ecc_level)
    return Capacity(
        format_version=format_version,
        geometry_version=geometry_version,
        alphabet=alphabet,
        ecc_level=ecc_level,
        payload_cells=payload_cells,
        channel_bits=channel_bits,
        channel_bytes=channel_bytes,
        maximum_frame_bytes=maximum_frame,
        maximum_uncompressed_payload_bytes=max(0, maximum_frame - FRAME_FIXED_OVERHEAD),
    )


def choose_geometry(
    frame_length: int,
    *,
    alphabet: Alphabet = Alphabet.COLOR4,
    ecc_level: EccLevel = EccLevel.BALANCED,
    format_version: int = FORMAT_VERSION,
) -> int:
    if frame_length < 0:
        raise ValueError("frame_length must not be negative")
    for version in GEOMETRY_SELECTION_ORDER:
        capacity = capacity_for(version, alphabet, ecc_level, format_version=format_version)
        if encoded_length(frame_length, ecc_level) <= capacity.channel_bytes:
            return version
    largest = capacity_for(
        GEOMETRY_SELECTION_ORDER[-1], alphabet, ecc_level, format_version=format_version
    )
    raise ValueError(
        f"frame requires {encoded_length(frame_length, ecc_level)} channel bytes; "
        f"largest geometry provides {largest.channel_bytes}"
    )
