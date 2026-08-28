"""Reference decoder for canonical, front-facing RadialCode images."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from math import cos, exp, pi, sin
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Iterable, Sequence

import numpy as np
from PIL import Image

from .bootstrap import (
    HEADER_SLOT_OFFSETS,
    header_codeword_from_physical,
    header_codeword_majority_from_physical,
)
from .channel import decode_symbols, permutation_seed
from .color import ColorClassification, classification_erasure, fit_color_model
from .constants import (
    HEADER_PHYSICAL_SLOTS,
    HEADER_RINGS,
    OUTER_HEADER_RING,
    MONO_PALETTE,
    PALETTES,
    QUIET_ZONE_OUTER,
    Alphabet,
)
from .ecc import decode as rs_decode
from .ecc import encoded_length
from .framing import PayloadFrame, decode_frame
from .geometry import CellAddress, PolarCell, RadialGeometry, geometry_for_format
from .header import HeaderError, RadialHeader
from .interleave import (
    deinterleave_rs_blocks,
    interleaved_to_concatenated_positions,
    spatial_permutation,
)

TAU = 2.0 * pi


class DecodeError(ValueError):
    """Raised when a canonical image cannot be decoded."""


@dataclass(frozen=True, slots=True)
class CellDiagnostic:
    address: CellAddress
    symbol: int
    confidence: float
    second_symbol: int
    second_confidence: float


@dataclass(frozen=True, slots=True)
class DecodeDiagnostics:
    decode_success: bool
    geometry_version: int
    alphabet: Alphabet
    payload_size: int
    ecc_level: int
    header_corrected_bits: tuple[int, ...]
    corrected_rs_symbols: int
    erasure_cells: int
    erasure_bytes: int
    average_confidence: float
    minimum_confidence: float
    processing_time_ms: float
    color_reference_means: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True, slots=True)
class DecodedRadialCode:
    payload: bytes
    frame: PayloadFrame
    header: RadialHeader
    diagnostics: DecodeDiagnostics
    cells: tuple[CellDiagnostic, ...]

    def text(self) -> str:
        return self.payload.decode("utf-8")



def _load_rgb(image: str | Path | bytes | Image.Image) -> np.ndarray:
    if isinstance(image, (str, Path)):
        loaded = Image.open(image)
    elif isinstance(image, bytes):
        loaded = Image.open(BytesIO(image))
    elif isinstance(image, Image.Image):
        loaded = image
    else:
        raise TypeError("image must be a path, PNG bytes or PIL Image")

    if loaded.mode == "RGBA":
        background = Image.new("RGBA", loaded.size, (255, 255, 255, 255))
        background.alpha_composite(loaded)
        loaded = background.convert("RGB")
    else:
        loaded = loaded.convert("RGB")
    array = np.asarray(loaded, dtype=np.float64)
    if array.ndim != 3 or array.shape[2] != 3:
        raise DecodeError("image did not convert to RGB")
    return array


def _canonical_center_radius(array: np.ndarray) -> tuple[float, float, float]:
    height, width = array.shape[:2]
    if min(height, width) < 64:
        raise DecodeError("canonical image is too small")
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    functional_radius = min(width, height) / (2.0 * QUIET_ZONE_OUTER)
    return center_x, center_y, functional_radius


def _sample_patch(
    array: np.ndarray,
    *,
    normalized_radius: float,
    theta: float,
    patch_radius: int = 1,
) -> tuple[float, float, float]:
    center_x, center_y, functional_radius = _canonical_center_radius(array)
    x = center_x + normalized_radius * functional_radius * sin(theta)
    y = center_y - normalized_radius * functional_radius * cos(theta)
    ix = int(round(x))
    iy = int(round(y))
    x0 = max(0, ix - patch_radius)
    x1 = min(array.shape[1], ix + patch_radius + 1)
    y0 = max(0, iy - patch_radius)
    y1 = min(array.shape[0], iy + patch_radius + 1)
    patch = array[y0:y1, x0:x1]
    if patch.size == 0:
        raise DecodeError("sample point lies outside the image")
    mean = np.mean(patch.reshape(-1, 3), axis=0)
    return float(mean[0]), float(mean[1]), float(mean[2])


def _sample_cell(array: np.ndarray, cell: PolarCell) -> tuple[float, float, float]:
    _, _, functional_radius = _canonical_center_radius(array)
    radial_pixels = (cell.r_outer - cell.r_inner) * functional_radius
    patch_radius = max(0, min(2, int(radial_pixels * 0.14)))
    return _sample_patch(
        array,
        normalized_radius=cell.r_center,
        theta=cell.theta_center,
        patch_radius=patch_radius,
    )


def _sample_cells(array: np.ndarray, cells: Sequence[PolarCell]) -> np.ndarray:
    if not cells:
        return np.empty((0, 3), dtype=np.float64)
    center_x, center_y, functional_radius = _canonical_center_radius(array)
    radii = np.asarray([cell.r_center for cell in cells], dtype=np.float64) * functional_radius
    theta = np.asarray([cell.theta_center for cell in cells], dtype=np.float64)
    x = np.rint(center_x + radii * np.sin(theta)).astype(np.int64)
    y = np.rint(center_y - radii * np.cos(theta)).astype(np.int64)
    radial_pixels = np.asarray([cell.r_outer - cell.r_inner for cell in cells], dtype=np.float64) * functional_radius
    patch_radii = np.clip((radial_pixels * 0.14).astype(np.int64), 0, 2)
    x0 = np.maximum(0, x - patch_radii)
    x1 = np.minimum(array.shape[1], x + patch_radii + 1)
    y0 = np.maximum(0, y - patch_radii)
    y1 = np.minimum(array.shape[0], y + patch_radii + 1)
    integral = np.pad(array, ((1, 0), (1, 0), (0, 0)), mode="constant").cumsum(axis=0).cumsum(axis=1)
    sums = integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
    areas = ((x1 - x0) * (y1 - y0)).astype(np.float64)
    return sums / areas[:, None]


def _luma(rgb: Sequence[float]) -> float:
    red, green, blue = rgb
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _adaptive_binary_threshold(values: Sequence[float]) -> float:
    if not values:
        raise DecodeError("cannot threshold an empty sample set")
    low = min(values)
    high = max(values)
    for _ in range(12):
        midpoint = (low + high) / 2.0
        low_group = [value for value in values if value <= midpoint]
        high_group = [value for value in values if value > midpoint]
        if not low_group or not high_group:
            break
        next_low = fmean(low_group)
        next_high = fmean(high_group)
        if abs(next_low - low) + abs(next_high - high) < 0.01:
            low, high = next_low, next_high
            break
        low, high = next_low, next_high
    if high - low < 4.0:
        raise DecodeError("header ring has insufficient luminance separation")
    return (low + high) / 2.0


def _sample_header_ring(array: np.ndarray, copy_index: int) -> tuple[int, ...]:
    r_inner, r_outer = HEADER_RINGS[copy_index]
    radius = (r_inner + r_outer) / 2.0
    luminances: list[float] = []
    for slot in range(HEADER_PHYSICAL_SLOTS):
        theta = (slot + 0.5) * TAU / HEADER_PHYSICAL_SLOTS
        rgb = _sample_patch(array, normalized_radius=radius, theta=theta, patch_radius=0)
        luminances.append(_luma(rgb))
    threshold = _adaptive_binary_threshold(luminances)
    return tuple(1 if value < threshold else 0 for value in luminances)


def _sample_outer_header_ring(array: np.ndarray, radius: float) -> tuple[int, ...]:
    luminances = [
        _luma(_sample_patch(array, normalized_radius=radius, theta=(slot + 0.5) * TAU / HEADER_PHYSICAL_SLOTS, patch_radius=0))
        for slot in range(HEADER_PHYSICAL_SLOTS)
    ]
    threshold = _adaptive_binary_threshold(luminances)
    return tuple(1 if value < threshold else 0 for value in luminances)


def _decode_header(array: np.ndarray) -> tuple[RadialHeader, tuple[int, ...]]:
    successes: list[tuple[RadialHeader, int]] = []
    sampled_copies: list[tuple[int, tuple[int, ...]]] = []
    for copy_index in range(3):
        try:
            bits = _sample_header_ring(array, copy_index)
        except DecodeError:
            # A local visual obstruction can remove the luminance separation of
            # one concentric copy. The remaining BCH copies are independent and
            # retain the same voting contract, so treat this copy as unavailable.
            continue
        sampled_copies.append((copy_index, bits))
        codeword = header_codeword_from_physical(bits, copy_index)
        try:
            header, corrected = RadialHeader.decode_codeword(codeword)
        except (HeaderError, ValueError):
            continue
        successes.append((header, corrected))

    if not successes and len(sampled_copies) == 3:
        ordered = tuple(bits for _, bits in sorted(sampled_copies))
        try:
            header, corrected = RadialHeader.decode_codeword(header_codeword_majority_from_physical(ordered))
        except (HeaderError, ValueError):
            pass
        else:
            successes.append((header, corrected))

    if not successes:
        # The fourth copy occupies a stable radial gap outside the three
        # historical rings. The small radius tolerance covers subpixel
        # rectification without sampling the adjacent data field.
        outer_center = (OUTER_HEADER_RING[0] + OUTER_HEADER_RING[1]) / 2.0
        for radius in tuple(outer_center + delta for delta in (-0.008, -0.006, -0.004, -0.002, 0.0, 0.002, 0.004, 0.006, 0.008)):
            try:
                bits = _sample_outer_header_ring(array, radius)
                header, corrected = RadialHeader.decode_codeword(header_codeword_from_physical(bits, 3))
            except (DecodeError, HeaderError, ValueError):
                continue
            if header.format_version >= 5:
                successes.append((header, corrected))
                break

    if not successes:
        raise DecodeError("all three BCH header copies failed")
    counts = Counter(header for header, _ in successes)
    selected, votes = counts.most_common(1)[0]
    if votes < 2 and len(successes) > 1:
        raise DecodeError("header copies decoded to inconsistent values")
    corrected = tuple(count for header, count in successes if header == selected)
    return selected, corrected


def _color_payload_samples(
    array: np.ndarray,
    geometry: RadialGeometry,
    alphabet: Alphabet,
) -> tuple[list[int], list[float], list[CellDiagnostic], tuple[tuple[float, float, float], ...]]:
    if geometry.version.number == 1:
        references = geometry.calibration_addresses(alphabet)
        grouped: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
        for address, state in references.items():
            grouped[state].append(_sample_cell(array, geometry.cell(address)))
        model = fit_color_model(grouped, regularization=36.0)
        symbols: list[int] = []
        confidences: list[float] = []
        diagnostics: list[CellDiagnostic] = []
        for address in geometry.payload_addresses(alphabet):
            sample = _sample_cell(array, geometry.cell(address))
            classification = model.classify(sample)
            symbols.append(classification.symbol)
            confidences.append(min(classification.confidence, _color_visibility_confidence(sample)))
            diagnostics.append(
                CellDiagnostic(
                    address=address,
                    symbol=classification.symbol,
                    confidence=classification.confidence,
                    second_symbol=classification.second_symbol,
                    second_confidence=classification.second_confidence,
                )
            )
        reference_means = tuple(tuple(float(value) for value in row) for row in model.means)
        return symbols, confidences, diagnostics, reference_means

    references = geometry.calibration_addresses(alphabet)
    grouped: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    for address, state in references.items():
        grouped[state].append(_sample_cell(array, geometry.cell(address)))
    model = fit_color_model(grouped, regularization=36.0)

    addresses = geometry.payload_addresses(alphabet)
    samples = _sample_cells(array, [geometry.cell(address) for address in addresses])
    classifications = model.classify_many(samples)
    black_occlusion_indices = _large_neutral_black_components(samples, addresses, geometry)
    symbols = [classification.symbol for classification in classifications]
    confidences = [
        min(classification.confidence, _color_visibility_confidence(sample), 0.0 if index in black_occlusion_indices else 1.0)
        for index, (classification, sample) in enumerate(zip(classifications, samples, strict=True))
    ]
    diagnostics = [
            CellDiagnostic(
                address=address,
                symbol=classification.symbol,
                confidence=classification.confidence,
                second_symbol=classification.second_symbol,
                second_confidence=classification.second_confidence,
            )
        for address, classification in zip(addresses, classifications, strict=True)
    ]
    reference_means = tuple(tuple(float(value) for value in row) for row in model.means)
    return symbols, confidences, diagnostics, reference_means


def _color_visibility_confidence(rgb: Sequence[float]) -> float:
    """Return zero for neutral white occlusions outside every registered COLOR4 state.

    A white overlay can look relatively closest to yellow after reference model
    drift, even though it is not a valid COLOR4 state. Registered palette yellow
    remains strongly chromatic, so an almost-neutral highlight is safe to expose
    to RS as an erasure.
    """

    channels = tuple(float(value) for value in rgb)
    if min(channels) >= 225.0 and max(channels) - min(channels) <= 24.0:
        return 0.0
    return 1.0


def _large_neutral_black_components(
    samples: Sequence[Sequence[float]],
    addresses: Sequence[CellAddress],
    geometry: RadialGeometry,
) -> set[int]:
    """Identify a pasted black patch without treating ordinary black cells as damaged.

    Format 4 uses constant angular columns. A black overlay therefore creates a
    contiguous two-dimensional block of neutral black samples, unlike normal
    scrambled COLOR4 payloads whose black cells are spatially dispersed. This is
    deliberately restricted to the new grid so legacy layouts retain their
    existing classifier behavior.
    """

    if geometry.format_version < 4 or len(set(geometry.sector_counts)) != 1:
        return set()
    candidate_indices = {
        index
        for index, sample in enumerate(samples)
        if max(sample) <= 42.0 and max(sample) - min(sample) <= 16.0
    }
    if len(candidate_indices) < 12:
        return set()
    address_to_index = {address: index for index, address in enumerate(addresses)}
    sectors = geometry.sector_counts[0]
    components: list[set[int]] = []
    remaining = set(candidate_indices)
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            index = stack.pop()
            address = addresses[index]
            neighbors = (
                CellAddress(address.ring, (address.sector - 1) % sectors),
                CellAddress(address.ring, (address.sector + 1) % sectors),
                CellAddress(address.ring - 1, address.sector),
                CellAddress(address.ring + 1, address.sector),
            )
            for neighbor in neighbors:
                neighbor_index = address_to_index.get(neighbor)
                if neighbor_index is not None and neighbor_index in remaining:
                    remaining.remove(neighbor_index)
                    component.add(neighbor_index)
                    stack.append(neighbor_index)
        components.append(component)
    return set().union(*(component for component in components if len(component) >= 12))


def _mono_payload_samples(
    array: np.ndarray,
    geometry: RadialGeometry,
) -> tuple[list[int], list[float], list[CellDiagnostic], tuple[tuple[float, float, float], ...]]:
    addresses = geometry.payload_addresses(Alphabet.MONO2)
    samples = _sample_cells(array, [geometry.cell(address) for address in addresses])
    symbols: list[int] = []
    confidences: list[float] = []
    diagnostics: list[CellDiagnostic] = []
    for address, rgb in zip(addresses, samples, strict=True):
        value = _luma(rgb)
        symbol = 1 if value < 128.0 else 0
        confidence = min(1.0, abs(value - 127.5) / 127.5)
        symbols.append(symbol)
        confidences.append(confidence)
        diagnostics.append(
            CellDiagnostic(
                address=address,
                symbol=symbol,
                confidence=confidence,
                second_symbol=1 - symbol,
                second_confidence=1.0 - confidence,
            )
        )
    means = ((255.0, 255.0, 255.0), (17.0, 17.0, 17.0))
    return symbols, confidences, diagnostics, means


@lru_cache(maxsize=12)
def _cached_geometry(version: int, format_version: int) -> RadialGeometry:
    return geometry_for_format(version, format_version)


def _erasure_positions(
    confidences: Sequence[float],
    *,
    threshold: float,
    geometry: RadialGeometry,
    header: RadialHeader,
    rs_byte_length: int,
) -> tuple[set[int], int]:
    addresses = geometry.payload_addresses(header.alphabet)
    seed = permutation_seed(
        geometry_version=header.geometry_version,
        format_version=header.format_version,
        alphabet=header.alphabet,
        ecc_level=int(header.ecc_level),
        frame_length=header.encoded_payload_length,
    )
    permutation = spatial_permutation(len(addresses), seed=seed)
    bits_per_cell = header.alphabet.bits_per_cell
    low_physical = {index for index, value in enumerate(confidences) if value < threshold}
    low_logical = {
        logical_index
        for logical_index, physical_index in enumerate(permutation)
        if physical_index in low_physical
    }
    interleaved_bytes: set[int] = set()
    for logical_index in low_logical:
        first_bit = logical_index * bits_per_cell
        last_bit = first_bit + bits_per_cell - 1
        for byte_index in range(first_bit // 8, last_bit // 8 + 1):
            if byte_index < rs_byte_length:
                interleaved_bytes.add(byte_index)

    position_map = interleaved_to_concatenated_positions(
        data_length=header.encoded_payload_length,
        level=header.ecc_level,
    )
    rs_positions = {position_map[index] for index in interleaved_bytes}
    return rs_positions, len(low_physical)


def decode_canonical(
    image: str | Path | bytes | Image.Image,
    *,
    geometry_hint: int | None = None,
    erasure_threshold: float = 0.55,
) -> DecodedRadialCode:
    """Decode a centered, front-facing symbol with its full quiet zone."""

    started = perf_counter()
    if not 0.0 <= erasure_threshold <= 1.0:
        raise ValueError("erasure_threshold must be between zero and one")
    array = _load_rgb(image)
    header, header_corrections = _decode_header(array)
    if geometry_hint is not None and header.geometry_version != geometry_hint:
        raise DecodeError(
            f"geometry hint {geometry_hint} conflicts with header version {header.geometry_version}"
        )
    geometry = _cached_geometry(header.geometry_version, header.format_version)

    if header.alphabet is Alphabet.COLOR4:
        physical_symbols, confidences, cells, reference_means = _color_payload_samples(
            array, geometry, header.alphabet
        )
    elif header.alphabet is Alphabet.MONO2:
        physical_symbols, confidences, cells, reference_means = _mono_payload_samples(array, geometry)
    else:
        raise DecodeError(f"unsupported alphabet in canonical decoder: {header.alphabet.name}")

    rs_byte_length = encoded_length(header.encoded_payload_length, header.ecc_level)
    interleaved = decode_symbols(
        physical_symbols,
        geometry=geometry,
        alphabet=header.alphabet,
        ecc_level=int(header.ecc_level),
        frame_length=header.encoded_payload_length,
        mask_id=header.mask_id,
        encoded_byte_length=rs_byte_length,
    )
    rs_positions, erasure_cells = _erasure_positions(
        confidences,
        threshold=erasure_threshold,
        geometry=geometry,
        header=header,
        rs_byte_length=rs_byte_length,
    )
    concatenated = deinterleave_rs_blocks(
        interleaved,
        data_length=header.encoded_payload_length,
        level=header.ecc_level,
    )
    ecc_result = rs_decode(
        concatenated,
        data_length=header.encoded_payload_length,
        level=header.ecc_level,
        erasure_positions=rs_positions,
    )
    frame = decode_frame(ecc_result.data)
    elapsed_ms = (perf_counter() - started) * 1000.0
    average_confidence = fmean(confidences) if confidences else 1.0
    minimum_confidence = min(confidences, default=1.0)
    diagnostics = DecodeDiagnostics(
        decode_success=True,
        geometry_version=header.geometry_version,
        alphabet=header.alphabet,
        payload_size=len(frame.payload),
        ecc_level=int(header.ecc_level),
        header_corrected_bits=header_corrections,
        corrected_rs_symbols=ecc_result.corrected_symbols,
        erasure_cells=erasure_cells,
        erasure_bytes=len(rs_positions),
        average_confidence=average_confidence,
        minimum_confidence=minimum_confidence,
        processing_time_ms=elapsed_ms,
        color_reference_means=reference_means,
    )
    return DecodedRadialCode(
        payload=frame.payload,
        frame=frame,
        header=header,
        diagnostics=diagnostics,
        cells=tuple(cells),
    )
