"""Map interleaved channel bytes to masked visual symbols."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

from .constants import Alphabet
from .geometry import CellAddress, RadialGeometry, geometry_for_format
from .interleave import XorShift32, apply_permutation, reverse_permutation, spatial_permutation


@dataclass(frozen=True, slots=True)
class MaskScore:
    mask_id: int
    total: float
    imbalance: float
    angular_runs: float
    radial_repetition: float



def bytes_to_bits(data: bytes) -> list[int]:
    return [(byte >> shift) & 1 for byte in data for shift in range(7, -1, -1)]


def bits_to_bytes(bits: Sequence[int], *, byte_length: int) -> bytes:
    required = byte_length * 8
    if len(bits) < required:
        raise ValueError(f"insufficient bits: required {required}, got {len(bits)}")
    output = bytearray()
    for offset in range(0, required, 8):
        value = 0
        for bit in bits[offset : offset + 8]:
            if bit not in (0, 1):
                raise ValueError("bits must contain only 0 and 1")
            value = (value << 1) | bit
        output.append(value)
    return bytes(output)


def bits_to_symbols(bits: Sequence[int], bits_per_cell: int) -> list[int]:
    if bits_per_cell not in (1, 2, 3):
        raise ValueError("bits_per_cell must be 1, 2 or 3")
    symbols: list[int] = []
    for offset in range(0, len(bits), bits_per_cell):
        value = 0
        chunk = list(bits[offset : offset + bits_per_cell])
        if len(chunk) < bits_per_cell:
            chunk.extend([0] * (bits_per_cell - len(chunk)))
        for bit in chunk:
            value = (value << 1) | bit
        symbols.append(value)
    return symbols


def symbols_to_bits(symbols: Sequence[int], bits_per_cell: int) -> list[int]:
    states = 1 << bits_per_cell
    bits: list[int] = []
    for symbol in symbols:
        if not 0 <= symbol < states:
            raise ValueError(f"symbol {symbol} does not fit in {bits_per_cell} bits")
        bits.extend((symbol >> shift) & 1 for shift in range(bits_per_cell - 1, -1, -1))
    return bits


def permutation_seed(
    *,
    geometry_version: int,
    alphabet: Alphabet,
    ecc_level: int,
    frame_length: int,
    format_version: int = 2,
) -> int:
    seed = 0x52414449  # ASCII "RADI"
    seed ^= (geometry_version & 0xFF) << 24
    seed ^= (int(alphabet) & 0x0F) << 20
    seed ^= (ecc_level & 0x0F) << 16
    seed ^= frame_length & 0xFFFF
    if format_version >= 3:
        seed ^= (format_version & 0x0F) << 12
    return seed & 0xFFFFFFFF


def _padding_symbols(count: int, *, states: int, seed: int) -> list[int]:
    rng = XorShift32(seed ^ 0xA5C31E27)
    return [rng.randbelow(states) for _ in range(count)]


def mask_value(mask_id: int, address: CellAddress, bits_per_cell: int) -> int:
    if not 0 <= mask_id <= 7:
        raise ValueError("mask_id must be between 0 and 7")
    ring = address.ring
    sector = address.sector
    output = 0
    for plane in range(bits_per_cell):
        if mask_id == 0:
            bit = (ring + sector + plane) & 1
        elif mask_id == 1:
            bit = (ring + plane) & 1
        elif mask_id == 2:
            bit = 1 if (sector + plane) % 3 == 0 else 0
        elif mask_id == 3:
            bit = 1 if (ring + sector + plane) % 3 == 0 else 0
        elif mask_id == 4:
            bit = ((ring // 2) + (sector // 3) + plane) & 1
        elif mask_id == 5:
            product = (ring + 1) * (sector + 1 + plane)
            bit = 1 if (product % 2) + (product % 3) == 0 else 0
        elif mask_id == 6:
            product = (ring + 1) * (sector + 1 + plane)
            bit = ((product % 2) + (product % 3)) & 1
        else:
            product = (ring + 1) * (sector + 1 + plane)
            bit = (((ring + sector + plane) % 2) + (product % 3)) & 1
        output = (output << 1) | bit
    return output


def apply_mask(symbols: Sequence[int], addresses: Sequence[CellAddress], *, mask_id: int, bits_per_cell: int) -> list[int]:
    if len(symbols) != len(addresses):
        raise ValueError("symbols and addresses must have equal length")
    return [
        symbol ^ mask_value(mask_id, address, bits_per_cell)
        for symbol, address in zip(symbols, addresses, strict=True)
    ]


def _score_masked(
    geometry: RadialGeometry,
    addresses: Sequence[CellAddress],
    symbols: Sequence[int],
    *,
    states: int,
    mask_id: int,
) -> MaskScore:
    by_address = dict(zip(addresses, symbols, strict=True))
    counts = Counter(symbols)
    target = len(symbols) / states if states else 0.0
    imbalance = sum(abs(counts[state] - target) for state in range(states)) / max(1.0, len(symbols))

    angular_runs = 0.0
    by_ring: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for address, symbol in by_address.items():
        by_ring[address.ring].append((address.sector, symbol))
    for values in by_ring.values():
        ordered = [symbol for _, symbol in sorted(values)]
        if not ordered:
            continue
        run = 1
        for previous, current in zip(ordered, ordered[1:]):
            if current == previous:
                run += 1
            else:
                if run >= 5:
                    angular_runs += float((run - 4) ** 2)
                run = 1
        if run >= 5:
            angular_runs += float((run - 4) ** 2)

    radial_repetition = 0.0
    for cell in geometry.cells:
        symbol = by_address.get(cell.address)
        if symbol is None or cell.address.ring == 0:
            continue
        inner_sectors = geometry.sector_counts[cell.address.ring - 1]
        nearest_sector = int(round((cell.theta_center / (2.0 * 3.141592653589793)) * inner_sectors)) % inner_sectors
        neighbor = by_address.get(CellAddress(cell.address.ring - 1, nearest_sector))
        if neighbor == symbol:
            radial_repetition += 1.0

    normalized_runs = angular_runs / max(1.0, len(symbols))
    normalized_radial = radial_repetition / max(1.0, len(symbols))
    total = 100.0 * imbalance + 20.0 * normalized_runs + 5.0 * normalized_radial
    return MaskScore(mask_id, total, imbalance, normalized_runs, normalized_radial)


@dataclass(frozen=True, slots=True)
class _MaskLayout:
    addresses: tuple[CellAddress, ...]
    mask_values: tuple[tuple[int, ...], ...]
    ring_indices: tuple[tuple[int, ...], ...]
    radial_neighbors: tuple[int, ...]


@lru_cache(maxsize=32)
def _mask_layout(geometry_version: int, format_version: int, alphabet: Alphabet) -> _MaskLayout:
    geometry = geometry_for_format(geometry_version, format_version)
    addresses = tuple(geometry.payload_addresses(alphabet))
    index_by_address = {address: index for index, address in enumerate(addresses)}
    by_ring: dict[int, list[int]] = defaultdict(list)
    for index, address in enumerate(addresses):
        by_ring[address.ring].append(index)
    ring_indices = tuple(
        tuple(sorted(indices, key=lambda index: addresses[index].sector))
        for _, indices in sorted(by_ring.items())
    )
    neighbors: list[int] = []
    for address in addresses:
        if address.ring == 0:
            neighbors.append(-1)
            continue
        cell = geometry.cell(address)
        inner_sectors = geometry.sector_counts[address.ring - 1]
        nearest_sector = int(round((cell.theta_center / (2.0 * 3.141592653589793)) * inner_sectors)) % inner_sectors
        neighbors.append(index_by_address.get(CellAddress(address.ring - 1, nearest_sector), -1))
    values = tuple(
        tuple(mask_value(mask_id, address, alphabet.bits_per_cell) for address in addresses)
        for mask_id in range(8)
    )
    return _MaskLayout(addresses, values, ring_indices, tuple(neighbors))


def _score_masked_layout(
    layout: _MaskLayout,
    symbols: Sequence[int],
    *,
    states: int,
    mask_id: int,
) -> MaskScore:
    counts = Counter(symbols)
    target = len(symbols) / states if states else 0.0
    imbalance = sum(abs(counts[state] - target) for state in range(states)) / max(1.0, len(symbols))
    angular_runs = 0.0
    for indices in layout.ring_indices:
        if not indices:
            continue
        run = 1
        for previous_index, current_index in zip(indices, indices[1:]):
            if symbols[current_index] == symbols[previous_index]:
                run += 1
            else:
                if run >= 5:
                    angular_runs += float((run - 4) ** 2)
                run = 1
        if run >= 5:
            angular_runs += float((run - 4) ** 2)
    radial_repetition = sum(
        1.0
        for index, neighbor in enumerate(layout.radial_neighbors)
        if neighbor >= 0 and symbols[neighbor] == symbols[index]
    )
    normalized_runs = angular_runs / max(1.0, len(symbols))
    normalized_radial = radial_repetition / max(1.0, len(symbols))
    total = 100.0 * imbalance + 20.0 * normalized_runs + 5.0 * normalized_radial
    return MaskScore(mask_id, total, imbalance, normalized_runs, normalized_radial)


@dataclass(frozen=True, slots=True)
class ChannelSymbols:
    symbols: tuple[int, ...]
    mask_id: int
    mask_scores: tuple[MaskScore, ...]
    permutation: tuple[int, ...]
    encoded_symbol_count: int


def encode_symbols(
    encoded_bytes: bytes,
    *,
    geometry: RadialGeometry,
    alphabet: Alphabet,
    ecc_level: int,
    frame_length: int,
) -> ChannelSymbols:
    layout = _mask_layout(geometry.version.number, geometry.format_version, alphabet)
    addresses = layout.addresses
    bits_per_cell = alphabet.bits_per_cell
    states = 1 << bits_per_cell
    data_symbols = bits_to_symbols(bytes_to_bits(encoded_bytes), bits_per_cell)
    if len(data_symbols) > len(addresses):
        raise ValueError(
            f"encoded payload needs {len(data_symbols)} cells, but geometry provides {len(addresses)}"
        )

    seed = permutation_seed(
        geometry_version=geometry.version.number,
        alphabet=alphabet,
        ecc_level=ecc_level,
        frame_length=frame_length,
        format_version=geometry.format_version,
    )
    padded = data_symbols + _padding_symbols(len(addresses) - len(data_symbols), states=states, seed=seed)
    permutation = spatial_permutation(len(addresses), seed=seed)
    physical_unmasked = apply_permutation(padded, permutation)

    candidates: list[tuple[MaskScore, list[int]]] = []
    for mask_id in range(8):
        masked = [
            symbol ^ mask
            for symbol, mask in zip(physical_unmasked, layout.mask_values[mask_id], strict=True)
        ]
        score = _score_masked_layout(layout, masked, states=states, mask_id=mask_id)
        candidates.append((score, masked))
    candidates.sort(key=lambda item: (item[0].total, item[0].mask_id))
    best_score, best_symbols = candidates[0]
    all_scores = tuple(sorted((score for score, _ in candidates), key=lambda item: item.mask_id))
    return ChannelSymbols(
        symbols=tuple(best_symbols),
        mask_id=best_score.mask_id,
        mask_scores=all_scores,
        permutation=permutation,
        encoded_symbol_count=len(data_symbols),
    )


def decode_symbols(
    physical_symbols: Sequence[int],
    *,
    geometry: RadialGeometry,
    alphabet: Alphabet,
    ecc_level: int,
    frame_length: int,
    mask_id: int,
    encoded_byte_length: int,
) -> bytes:
    layout = _mask_layout(geometry.version.number, geometry.format_version, alphabet)
    addresses = layout.addresses
    if len(physical_symbols) != len(addresses):
        raise ValueError("physical symbol count does not match geometry")
    bits_per_cell = alphabet.bits_per_cell
    unmasked = [
        symbol ^ mask
        for symbol, mask in zip(physical_symbols, layout.mask_values[mask_id], strict=True)
    ]
    seed = permutation_seed(
        geometry_version=geometry.version.number,
        alphabet=alphabet,
        ecc_level=ecc_level,
        frame_length=frame_length,
        format_version=geometry.format_version,
    )
    permutation = spatial_permutation(len(addresses), seed=seed)
    logical = reverse_permutation(unmasked, permutation)
    required_symbols = (encoded_byte_length * 8 + bits_per_cell - 1) // bits_per_cell
    bits = symbols_to_bits(logical[:required_symbols], bits_per_cell)
    return bits_to_bytes(bits, byte_length=encoded_byte_length)
