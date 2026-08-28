"""High-level deterministic RadialCode encoder."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

from .capacity import choose_geometry
from .channel import ChannelSymbols, encode_symbols
from .constants import (
    FORMAT_VERSION,
    GEOMETRY_NAME_TO_VERSION,
    GEOMETRY_VERSIONS,
    Alphabet,
    EccLevel,
    PayloadType,
)
from .ecc import encode as rs_encode
from .framing import PayloadFrame, encode_frame
from .geometry import CellAddress, GeometryDiagnostics, RadialGeometry, geometry_for_format
from .header import RadialHeader
from .interleave import interleave_rs_blocks

ATTRIBUTION_TEXT = "Built with RadialCode — an open radial 2D code project."


@dataclass(frozen=True, slots=True)
class EncodedRadialCode:
    geometry: RadialGeometry
    diameter_mm: float
    alphabet: Alphabet
    ecc_level: EccLevel
    palette_id: int
    frame: PayloadFrame
    rs_encoded: bytes
    interleaved: bytes
    channel: ChannelSymbols
    header: RadialHeader
    cell_states: Mapping[CellAddress, int]
    diagnostics: GeometryDiagnostics

    @property
    def attribution(self) -> str:
        return ATTRIBUTION_TEXT

    @property
    def payload(self) -> bytes:
        return self.frame.payload


def _resolve_geometry(
    value: int | str,
    *,
    frame_length: int,
    alphabet: Alphabet,
    ecc_level: EccLevel,
    format_version: int,
) -> int:
    if value == "auto":
        return choose_geometry(
            frame_length,
            alphabet=alphabet,
            ecc_level=ecc_level,
            format_version=format_version,
        )
    if isinstance(value, str):
        try:
            return GEOMETRY_NAME_TO_VERSION[value.lower()].number
        except KeyError as exc:
            raise ValueError(f"unknown geometry name: {value}") from exc
    if value not in GEOMETRY_VERSIONS:
        raise ValueError(f"unsupported geometry version: {value}")
    return value


def _reserved_state(address: CellAddress, states: int) -> int:
    return (address.ring * 5 + address.sector * 3 + 1) % states


@lru_cache(maxsize=12)
def _cached_geometry(version: int, format_version: int) -> RadialGeometry:
    return geometry_for_format(version, format_version)


def encode(
    payload: bytes | str,
    *,
    geometry: int | str = "auto",
    diameter_mm: float | None = None,
    alphabet: Alphabet = Alphabet.COLOR4,
    ecc_level: EccLevel = EccLevel.BALANCED,
    palette_id: int = 0,
    payload_type: PayloadType | None = None,
    compression: str = "auto",
    format_version: int = FORMAT_VERSION,
) -> EncodedRadialCode:
    if alphabet not in (Alphabet.MONO2, Alphabet.COLOR4):
        raise ValueError("Protocol Draft 0.5 supports only MONO2 and COLOR4")

    frame = encode_frame(payload, payload_type=payload_type, compression=compression)
    geometry_version = _resolve_geometry(
        geometry,
        frame_length=len(frame.encoded_bytes),
        alphabet=alphabet,
        ecc_level=ecc_level,
        format_version=format_version,
    )
    radial_geometry = _cached_geometry(geometry_version, format_version)
    if diameter_mm is None:
        diameter_mm = radial_geometry.version.recommended_diameter_mm
    if diameter_mm <= 0:
        raise ValueError("diameter_mm must be positive")

    rs_encoded = rs_encode(frame.encoded_bytes, ecc_level)
    interleaved = interleave_rs_blocks(
        rs_encoded,
        data_length=len(frame.encoded_bytes),
        level=ecc_level,
    )
    channel = encode_symbols(
        interleaved,
        geometry=radial_geometry,
        alphabet=alphabet,
        ecc_level=int(ecc_level),
        frame_length=len(frame.encoded_bytes),
    )
    header = RadialHeader(
        format_version=format_version,
        geometry_version=geometry_version,
        alphabet=alphabet,
        palette_id=palette_id,
        ecc_level=ecc_level,
        mask_id=channel.mask_id,
        encoded_payload_length=len(frame.encoded_bytes),
    )

    cell_states: dict[CellAddress, int] = dict(
        zip(radial_geometry.payload_addresses(alphabet), channel.symbols, strict=True)
    )
    cell_states.update(radial_geometry.calibration_addresses(alphabet))
    states = 1 << alphabet.bits_per_cell
    for address in radial_geometry.future_reserved_addresses():
        cell_states[address] = _reserved_state(address, states)
    if len(cell_states) != radial_geometry.total_cells:
        raise AssertionError(
            f"cell assignment incomplete: assigned {len(cell_states)} of {radial_geometry.total_cells}"
        )

    return EncodedRadialCode(
        geometry=radial_geometry,
        diameter_mm=float(diameter_mm),
        alphabet=alphabet,
        ecc_level=ecc_level,
        palette_id=palette_id,
        frame=frame,
        rs_encoded=rs_encoded,
        interleaved=interleaved,
        channel=channel,
        header=header,
        cell_states=cell_states,
        diagnostics=radial_geometry.diagnostics(alphabet, float(diameter_mm)),
    )
