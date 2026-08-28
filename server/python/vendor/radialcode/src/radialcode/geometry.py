"""Deterministic polar geometry for RadialCode symbols."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Iterable

from .constants import (
    COLOR_REFERENCE_REPETITIONS,
    CONSTANT_COLUMNS_BY_GEOMETRY,
    CONSTANT_COLUMNS_DATA_INNER,
    DATA_INNER,
    DATA_OUTER,
    DATA_RESERVED_CELLS,
    FORMAT_VERSION,
    GEOMETRY_VERSIONS,
    GEOMETRY_IDS_BY_FORMAT,
    LEGACY_CONSTANT_COLUMNS_FORMAT_VERSION,
    LEGACY_FORMAT_VERSIONS,
    MIN_RING_SECTORS,
    PROVISIONAL_MIN_PRINT_PITCH_MM,
    ROUND_SECTOR_MULTIPLE,
    Alphabet,
    GeometryVersion,
)

TAU = 2.0 * pi


@dataclass(frozen=True, slots=True, order=True)
class CellAddress:
    ring: int
    sector: int


@dataclass(frozen=True, slots=True)
class PolarCell:
    address: CellAddress
    r_inner: float
    r_outer: float
    theta_start: float
    theta_end: float

    @property
    def r_center(self) -> float:
        return (self.r_inner + self.r_outer) / 2.0

    @property
    def theta_center(self) -> float:
        return (self.theta_start + self.theta_end) / 2.0


@dataclass(frozen=True, slots=True)
class GeometryDiagnostics:
    total_cells: int
    payload_cells: int
    reserved_cells: int
    calibration_cells: int
    normalized_pitch: float
    physical_pitch_mm: float
    print_pitch_warning: bool


def _round_to_multiple(value: float, multiple: int) -> int:
    rounded = int(value / multiple + 0.5) * multiple
    return max(MIN_RING_SECTORS, rounded)


class RadialGeometry:
    """Compute all logical slots for one geometry version.

    Ring indices increase from the inside out. Sector zero starts at 12 o'clock,
    and sector indices increase clockwise. Each ring receives a deterministic
    sub-cell angular offset to avoid long radial seams.
    """

    def __init__(
        self,
        version: int | GeometryVersion,
        *,
        format_version: int = 2,
        data_inner: float = DATA_INNER,
    ):
        if isinstance(version, int):
            try:
                version = GEOMETRY_VERSIONS[version]
            except KeyError as exc:
                raise ValueError(f"unsupported geometry version: {version}") from exc
        self.version = version
        self.format_version = format_version
        self.data_inner = data_inner
        self.radial_pitch = (DATA_OUTER - self.data_inner) / self.version.data_rings
        self._sector_counts = tuple(self._compute_sector_count(ring) for ring in range(self.version.data_rings))
        self._cells = tuple(self._build_cells())
        self._address_to_index = {cell.address: index for index, cell in enumerate(self._cells)}

    def _compute_sector_count(self, ring: int) -> int:
        radius = self.data_inner + (ring + 0.5) * self.radial_pitch
        ideal = TAU * radius / self.radial_pitch
        return _round_to_multiple(ideal, ROUND_SECTOR_MULTIPLE)

    @staticmethod
    def _ring_offset_fraction(ring: int) -> float:
        # An eight-step fractional-cell sequence. It is short, explicit and
        # reversible; visual and camera benchmarks may replace it before V1.
        return ((ring * 3) % 8) / 8.0

    def _build_cells(self) -> Iterable[PolarCell]:
        for ring, sectors in enumerate(self._sector_counts):
            r_inner = self.data_inner + ring * self.radial_pitch
            r_outer = r_inner + self.radial_pitch
            cell_angle = TAU / sectors
            offset = self._ring_offset_fraction(ring) * cell_angle
            for sector in range(sectors):
                theta_start = (offset + sector * cell_angle) % TAU
                theta_end = theta_start + cell_angle
                yield PolarCell(
                    address=CellAddress(ring, sector),
                    r_inner=r_inner,
                    r_outer=r_outer,
                    theta_start=theta_start,
                    theta_end=theta_end,
                )

    @property
    def sector_counts(self) -> tuple[int, ...]:
        return self._sector_counts

    @property
    def cells(self) -> tuple[PolarCell, ...]:
        return self._cells

    @property
    def total_cells(self) -> int:
        return len(self._cells)

    def cell(self, address: CellAddress) -> PolarCell:
        return self._cells[self._address_to_index[address]]

    def calibration_addresses(self, alphabet: Alphabet) -> dict[CellAddress, int]:
        if alphabet is Alphabet.MONO2:
            return {}
        states = 1 << alphabet.bits_per_cell
        ring_candidates = (
            0,
            max(0, self.version.data_rings // 3),
            max(0, (2 * self.version.data_rings) // 3),
            self.version.data_rings - 1,
        )[:COLOR_REFERENCE_REPETITIONS]
        references: dict[CellAddress, int] = {}
        for repetition, ring in enumerate(ring_candidates):
            sectors = self._sector_counts[ring]
            base = int(round((repetition / COLOR_REFERENCE_REPETITIONS) * sectors)) % sectors
            for state in range(states):
                address = CellAddress(ring, (base + state) % sectors)
                if address in references:
                    raise AssertionError("calibration address collision")
                references[address] = state
        return references

    def future_reserved_addresses(self) -> frozenset[CellAddress]:
        if DATA_RESERVED_CELLS <= 0:
            return frozenset()
        selected: set[CellAddress] = set()
        total = self.total_cells
        for index in range(DATA_RESERVED_CELLS):
            flat_index = min(total - 1, int((index + 0.5) * total / DATA_RESERVED_CELLS))
            selected.add(self._cells[flat_index].address)
        if len(selected) != DATA_RESERVED_CELLS:
            raise AssertionError("reserved address selection must be unique")
        return frozenset(selected)

    def payload_addresses(self, alphabet: Alphabet) -> tuple[CellAddress, ...]:
        excluded = set(self.future_reserved_addresses())
        excluded.update(self.calibration_addresses(alphabet))
        return tuple(cell.address for cell in self._cells if cell.address not in excluded)

    def physical_pitch_mm(self, diameter_mm: float) -> float:
        if diameter_mm <= 0:
            raise ValueError("diameter_mm must be positive")
        return self.radial_pitch * (diameter_mm / 2.0)

    def diagnostics(self, alphabet: Alphabet, diameter_mm: float) -> GeometryDiagnostics:
        calibration = len(self.calibration_addresses(alphabet))
        reserved = len(self.future_reserved_addresses())
        physical_pitch = self.physical_pitch_mm(diameter_mm)
        return GeometryDiagnostics(
            total_cells=self.total_cells,
            payload_cells=len(self.payload_addresses(alphabet)),
            reserved_cells=reserved,
            calibration_cells=calibration,
            normalized_pitch=self.radial_pitch,
            physical_pitch_mm=physical_pitch,
            print_pitch_warning=physical_pitch < PROVISIONAL_MIN_PRINT_PITCH_MM,
        )


class ConstantColumnGeometry(RadialGeometry):
    """Draft 0.4+ layout with one fixed angular column count per symbol."""

    def __init__(self, version: int | GeometryVersion, *, format_version: int = FORMAT_VERSION):
        version_number = version if isinstance(version, int) else version.number
        if version_number not in GEOMETRY_IDS_BY_FORMAT.get(format_version, frozenset()):
            raise ValueError(f"geometry {version_number} is not registered for format {format_version}")
        try:
            self.column_count = CONSTANT_COLUMNS_BY_GEOMETRY[version_number]
        except KeyError as exc:
            raise ValueError(f"unsupported geometry version: {version_number}") from exc
        super().__init__(
            version,
            format_version=format_version,
            data_inner=CONSTANT_COLUMNS_DATA_INNER,
        )

    def _compute_sector_count(self, ring: int) -> int:
        return self.column_count

    @staticmethod
    def _ring_offset_fraction(ring: int) -> float:
        return 0.0


def geometry_for_format(geometry_version: int, format_version: int = FORMAT_VERSION) -> RadialGeometry:
    """Construct the normative physical layout identified by the header format."""

    if format_version in LEGACY_FORMAT_VERSIONS:
        return RadialGeometry(geometry_version, format_version=format_version)
    if format_version in (LEGACY_CONSTANT_COLUMNS_FORMAT_VERSION, 4, FORMAT_VERSION):
        return ConstantColumnGeometry(geometry_version, format_version=format_version)
    raise ValueError(f"unsupported format version: {format_version}")
