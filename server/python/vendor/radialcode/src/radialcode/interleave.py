"""Deterministic byte and spatial interleaving."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from .constants import ECC_PROFILES, EccLevel
from .ecc import block_data_lengths, encoded_length

T = TypeVar("T")



def _encoded_block_lengths(data_length: int, level: EccLevel | int) -> tuple[int, ...]:
    profile = ECC_PROFILES[EccLevel(level)]
    return tuple(length + profile.parity_bytes for length in block_data_lengths(data_length, level))


def interleave_rs_blocks(encoded: bytes, *, data_length: int, level: EccLevel | int) -> bytes:
    """Interleave concatenated shortened RS blocks by byte column."""

    expected = encoded_length(data_length, level)
    if len(encoded) != expected:
        raise ValueError(f"encoded length mismatch: expected {expected}, got {len(encoded)}")

    blocks: list[bytes] = []
    offset = 0
    for length in _encoded_block_lengths(data_length, level):
        blocks.append(encoded[offset : offset + length])
        offset += length

    output = bytearray()
    for column in range(max((len(block) for block in blocks), default=0)):
        for block in blocks:
            if column < len(block):
                output.append(block[column])
    return bytes(output)


def interleaved_to_concatenated_positions(*, data_length: int, level: EccLevel | int) -> tuple[int, ...]:
    """Map each interleaved byte position to its concatenated RS position."""

    lengths = _encoded_block_lengths(data_length, level)
    offsets: list[int] = []
    cursor = 0
    for length in lengths:
        offsets.append(cursor)
        cursor += length
    mapping: list[int] = []
    for column in range(max(lengths, default=0)):
        for offset, length in zip(offsets, lengths, strict=True):
            if column < length:
                mapping.append(offset + column)
    return tuple(mapping)


def deinterleave_rs_blocks(interleaved: bytes, *, data_length: int, level: EccLevel | int) -> bytes:
    """Reverse :func:`interleave_rs_blocks` into concatenated RS blocks."""

    lengths = _encoded_block_lengths(data_length, level)
    expected = sum(lengths)
    if len(interleaved) != expected:
        raise ValueError(f"interleaved length mismatch: expected {expected}, got {len(interleaved)}")

    blocks = [bytearray(length) for length in lengths]
    cursor = 0
    for column in range(max(lengths, default=0)):
        for block, length in zip(blocks, lengths, strict=True):
            if column < length:
                block[column] = interleaved[cursor]
                cursor += 1
    if cursor != len(interleaved):
        raise AssertionError("internal RS deinterleaver cursor mismatch")
    return b"".join(bytes(block) for block in blocks)


class XorShift32:
    """Small normative PRNG used only for deterministic permutations/padding."""

    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF
        if self.state == 0:
            self.state = 0x6D2B79F5

    def next_u32(self) -> int:
        value = self.state
        value ^= (value << 13) & 0xFFFFFFFF
        value ^= value >> 17
        value ^= (value << 5) & 0xFFFFFFFF
        self.state = value & 0xFFFFFFFF
        return self.state

    def randbelow(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("upper must be positive")
        # Rejection sampling avoids modulo bias and is fully deterministic.
        limit = (1 << 32) - ((1 << 32) % upper)
        while True:
            value = self.next_u32()
            if value < limit:
                return value % upper



def spatial_permutation(length: int, *, seed: int) -> tuple[int, ...]:
    """Return a logical-index to physical-index permutation."""

    if length < 0:
        raise ValueError("length must not be negative")
    indices = list(range(length))
    rng = XorShift32(seed)
    for index in range(length - 1, 0, -1):
        swap = rng.randbelow(index + 1)
        indices[index], indices[swap] = indices[swap], indices[index]
    return tuple(indices)


def apply_permutation(values: Sequence[T], permutation: Sequence[int]) -> list[T]:
    if len(values) != len(permutation):
        raise ValueError("values and permutation must have equal length")
    output: list[T | None] = [None] * len(values)
    for logical_index, physical_index in enumerate(permutation):
        if not 0 <= physical_index < len(values):
            raise ValueError("permutation index out of range")
        if output[physical_index] is not None:
            raise ValueError("permutation contains duplicate positions")
        output[physical_index] = values[logical_index]
    if any(value is None for value in output):
        raise ValueError("permutation is incomplete")
    return [value for value in output if value is not None]


def reverse_permutation(values: Sequence[T], permutation: Sequence[int]) -> list[T]:
    if len(values) != len(permutation):
        raise ValueError("values and permutation must have equal length")
    output: list[T] = []
    for physical_index in permutation:
        if not 0 <= physical_index < len(values):
            raise ValueError("permutation index out of range")
        output.append(values[physical_index])
    return output
