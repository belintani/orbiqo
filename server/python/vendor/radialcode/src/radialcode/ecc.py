"""Reed–Solomon channel coding for RadialCode payload frames."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from reedsolo import RSCodec, ReedSolomonError

from .constants import ECC_PROFILES, EccLevel, EccProfile


class EccDecodeError(ValueError):
    """Raised when one or more RS blocks cannot be recovered."""


@dataclass(frozen=True, slots=True)
class BlockDiagnostics:
    block_index: int
    data_bytes: int
    parity_bytes: int
    corrected_symbols: int
    erasures_supplied: int


@dataclass(frozen=True, slots=True)
class EccDecodeResult:
    data: bytes
    blocks: tuple[BlockDiagnostics, ...]

    @property
    def corrected_symbols(self) -> int:
        return sum(block.corrected_symbols for block in self.blocks)

    @property
    def erasures_supplied(self) -> int:
        return sum(block.erasures_supplied for block in self.blocks)



def _profile(level: EccLevel | int) -> EccProfile:
    try:
        return ECC_PROFILES[EccLevel(level)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unsupported ECC level: {level}") from exc


def _codec(profile: EccProfile) -> RSCodec:
    return RSCodec(
        nsym=profile.parity_bytes,
        nsize=255,
        fcr=0,
        prim=0x11D,
        generator=2,
        c_exp=8,
        single_gen=True,
    )


def block_data_lengths(data_length: int, level: EccLevel | int) -> tuple[int, ...]:
    if data_length < 0:
        raise ValueError("data_length must not be negative")
    if data_length == 0:
        return ()
    profile = _profile(level)
    full_blocks, remainder = divmod(data_length, profile.data_bytes)
    lengths = [profile.data_bytes] * full_blocks
    if remainder:
        lengths.append(remainder)
    return tuple(lengths)


def encoded_length(data_length: int, level: EccLevel | int) -> int:
    profile = _profile(level)
    blocks = block_data_lengths(data_length, level)
    return data_length + len(blocks) * profile.parity_bytes


def encode(data: bytes, level: EccLevel | int) -> bytes:
    profile = _profile(level)
    codec = _codec(profile)
    output = bytearray()
    offset = 0
    for length in block_data_lengths(len(data), level):
        block = data[offset : offset + length]
        encoded = bytes(codec.encode(block))
        expected = length + profile.parity_bytes
        if len(encoded) != expected:
            raise AssertionError(f"unexpected RS encoded length: {len(encoded)} != {expected}")
        output.extend(encoded)
        offset += length
    return bytes(output)


def decode(
    encoded: bytes,
    *,
    data_length: int,
    level: EccLevel | int,
    erasure_positions: Iterable[int] = (),
) -> EccDecodeResult:
    profile = _profile(level)
    expected_length = encoded_length(data_length, level)
    if len(encoded) != expected_length:
        raise EccDecodeError(f"encoded length mismatch: expected {expected_length}, got {len(encoded)}")

    global_erasures = sorted(set(erasure_positions))
    if any(position < 0 or position >= len(encoded) for position in global_erasures):
        raise ValueError("erasure position is outside the encoded stream")

    codec = _codec(profile)
    output = bytearray()
    diagnostics: list[BlockDiagnostics] = []
    encoded_offset = 0

    for block_index, data_bytes in enumerate(block_data_lengths(data_length, level)):
        block_length = data_bytes + profile.parity_bytes
        block = encoded[encoded_offset : encoded_offset + block_length]
        local_erasures = [
            position - encoded_offset
            for position in global_erasures
            if encoded_offset <= position < encoded_offset + block_length
        ]
        try:
            message, repaired, errata = codec.decode(block, erase_pos=local_erasures)
        except ReedSolomonError as exc:
            raise EccDecodeError(f"RS block {block_index} is not recoverable") from exc

        if len(message) != data_bytes:
            raise EccDecodeError(
                f"RS block {block_index} returned {len(message)} data bytes; expected {data_bytes}"
            )
        if not all(codec.check(repaired)):
            raise EccDecodeError(f"RS block {block_index} failed post-correction syndrome check")

        output.extend(message)
        diagnostics.append(
            BlockDiagnostics(
                block_index=block_index,
                data_bytes=data_bytes,
                parity_bytes=profile.parity_bytes,
                corrected_symbols=len(errata),
                erasures_supplied=len(local_erasures),
            )
        )
        encoded_offset += block_length

    return EccDecodeResult(data=bytes(output), blocks=tuple(diagnostics))


def maximum_payload_for_encoded_capacity(encoded_capacity: int, level: EccLevel | int) -> int:
    """Return the largest data length whose shortened RS stream fits capacity."""

    if encoded_capacity < 0:
        raise ValueError("encoded_capacity must not be negative")
    profile = _profile(level)
    if encoded_capacity <= profile.parity_bytes:
        return 0

    # Start from the rate estimate, then adjust exactly around block boundaries.
    candidate = min(encoded_capacity, int(ceil(encoded_capacity * profile.code_rate)))
    while candidate > 0 and encoded_length(candidate, level) > encoded_capacity:
        candidate -= 1
    while encoded_length(candidate + 1, level) <= encoded_capacity:
        candidate += 1
    return candidate
