"""Monochrome bootstrap patterns: clock track, headers and anchors."""

from __future__ import annotations

from dataclasses import dataclass

from .bch import BCH_N, bits_to_int
from .constants import (
    ANCHOR_SLOTS,
    CLOCK_INITIAL_STATE,
    CLOCK_ORDER,
    CLOCK_SLOTS,
    CLOCK_TAP_MASK,
    HEADER_PHYSICAL_SLOTS,
)
from .header import RadialHeader


HEADER_SLOT_OFFSETS: tuple[int, int, int, int] = (0, 17, 43, 29)
HEADER_RESERVED_BITS: tuple[int, int, int, int] = (1, 0, 1, 0)



def msequence63(initial_state: int = CLOCK_INITIAL_STATE) -> tuple[int, ...]:
    """Generate the 63-chip maximum-length sequence for the Draft 0.3 clock.

    The six-bit register emits its most-significant bit. Feedback is the parity
    of ``CLOCK_TAP_MASK`` and the register shifts left, inserting feedback at
    the least-significant position.
    """

    state_limit = 1 << CLOCK_ORDER
    if not 0 < initial_state < state_limit:
        raise ValueError("initial_state must be a nonzero 6-bit value")
    state = initial_state
    sequence: list[int] = []
    seen: set[int] = set()
    period = state_limit - 1
    for _ in range(period):
        if state in seen:
            raise AssertionError("m-sequence repeated before 63 states")
        seen.add(state)
        output = (state >> (CLOCK_ORDER - 1)) & 1
        feedback = (state & CLOCK_TAP_MASK).bit_count() & 1
        state = ((state << 1) & (state_limit - 1)) | feedback
        sequence.append(output)
    if state != initial_state or len(seen) != period:
        raise AssertionError("clock polynomial/state did not produce period 63")
    return tuple(sequence)



def clock_track_bits() -> tuple[int, ...]:
    """Return 64 physical slots: one phase marker followed by 63 chips."""

    bits = (1,) + msequence63()
    if len(bits) != CLOCK_SLOTS:
        raise AssertionError("clock track length does not match CLOCK_SLOTS")
    return bits



def header_physical_bits(header: RadialHeader, copy_index: int) -> tuple[int, ...]:
    if not 0 <= copy_index < len(HEADER_SLOT_OFFSETS):
        raise ValueError("copy_index must be between 0 and 3")
    code_bits = header.codeword_bits()
    slots = [0] * HEADER_PHYSICAL_SLOTS
    reserved_slot = HEADER_SLOT_OFFSETS[copy_index]
    slots[reserved_slot] = HEADER_RESERVED_BITS[copy_index]
    for index, bit in enumerate(code_bits):
        slot = (reserved_slot + 1 + index) % HEADER_PHYSICAL_SLOTS
        slots[slot] = bit
    return tuple(slots)



def header_codeword_from_physical(bits: tuple[int, ...] | list[int], copy_index: int) -> int:
    if len(bits) != HEADER_PHYSICAL_SLOTS:
        raise ValueError("header physical ring must contain 64 bits")
    reserved_slot = HEADER_SLOT_OFFSETS[copy_index]
    code_bits = [bits[(reserved_slot + 1 + index) % HEADER_PHYSICAL_SLOTS] for index in range(BCH_N)]
    return bits_to_int(code_bits)


def header_codeword_majority_from_physical(
    copies: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]],
) -> int:
    """Vote codeword bits after undoing the three physical-ring rotations.

    Each concentric header copy uses a different physical offset. A localized
    obstruction therefore tends to damage different logical BCH positions in
    each ring. Majority voting restores positions that are clean in two copies.
    """

    if any(len(bits) != HEADER_PHYSICAL_SLOTS for bits in copies):
        raise ValueError("every header physical ring must contain 64 bits")
    logical_bits: list[int] = []
    for index in range(BCH_N):
        values = [
            copies[copy_index][(HEADER_SLOT_OFFSETS[copy_index] + 1 + index) % HEADER_PHYSICAL_SLOTS]
            for copy_index in range(3)
        ]
        logical_bits.append(1 if sum(values) >= 2 else 0)
    return bits_to_int(logical_bits)


@dataclass(frozen=True, slots=True)
class AnchorPattern:
    anchor_id: int
    center_slot: int
    width_slots: int



def anchor_patterns() -> tuple[AnchorPattern, ...]:
    return tuple(
        AnchorPattern(anchor_id=index, center_slot=slot, width_slots=3 + 2 * index)
        for index, slot in enumerate(ANCHOR_SLOTS)
    )
