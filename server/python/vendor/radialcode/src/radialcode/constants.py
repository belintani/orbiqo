"""Normative constants for the RadialCode Protocol Draft 0.5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


FORMAT_MAGIC = 0xD7
FORMAT_VERSION = 5
SUPPORTED_FORMAT_VERSIONS: tuple[int, ...] = (1, 2, 3, 4, 5)
LEGACY_FORMAT_VERSIONS: tuple[int, ...] = (1, 2)
LEGACY_CONSTANT_COLUMNS_FORMAT_VERSION = 3


class Alphabet(IntEnum):
    """Visual symbol alphabets supported by the reference implementation."""

    MONO2 = 0
    COLOR4 = 1
    COLOR8 = 2

    @property
    def bits_per_cell(self) -> int:
        return {Alphabet.MONO2: 1, Alphabet.COLOR4: 2, Alphabet.COLOR8: 3}[self]


class PayloadType(IntEnum):
    BINARY = 0
    UTF8 = 1
    URL = 2


class CompressionType(IntEnum):
    NONE = 0
    DEFLATE = 1


class EccScheme(IntEnum):
    RS_GF256 = 0


class EccLevel(IntEnum):
    FAST = 0
    BALANCED = 1
    ROBUST = 2
    EXTREME = 3


@dataclass(frozen=True, slots=True)
class EccProfile:
    level: EccLevel
    name: str
    data_bytes: int
    parity_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.data_bytes + self.parity_bytes

    @property
    def code_rate(self) -> float:
        return self.data_bytes / self.total_bytes


ECC_PROFILES: dict[EccLevel, EccProfile] = {
    EccLevel.FAST: EccProfile(EccLevel.FAST, "fast", 223, 32),
    EccLevel.BALANCED: EccProfile(EccLevel.BALANCED, "balanced", 191, 64),
    EccLevel.ROBUST: EccProfile(EccLevel.ROBUST, "robust", 159, 96),
    EccLevel.EXTREME: EccProfile(EccLevel.EXTREME, "extreme", 127, 128),
}


@dataclass(frozen=True, slots=True)
class GeometryVersion:
    number: int
    name: str
    data_rings: int
    recommended_diameter_mm: float


GEOMETRY_VERSIONS: dict[int, GeometryVersion] = {
    0: GeometryVersion(0, "micro-2", 2, 16.0),
    1: GeometryVersion(1, "small", 12, 30.0),
    2: GeometryVersion(2, "medium", 18, 40.0),
    3: GeometryVersion(3, "large", 24, 50.0),
    4: GeometryVersion(4, "xl", 30, 70.0),
    5: GeometryVersion(5, "micro-4", 4, 18.0),
    6: GeometryVersion(6, "micro-1", 1, 16.0),
}

GEOMETRY_NAME_TO_VERSION = {item.name: item for item in GEOMETRY_VERSIONS.values()}
GEOMETRY_SELECTION_ORDER: tuple[int, ...] = (6, 0, 5, 1, 2, 3, 4)
GEOMETRY_IDS_BY_FORMAT: dict[int, frozenset[int]] = {
    1: frozenset((1, 2, 3, 4)),
    2: frozenset((1, 2, 3, 4)),
    3: frozenset((1, 2, 3, 4)),
    4: frozenset(GEOMETRY_SELECTION_ORDER),
    5: frozenset(GEOMETRY_SELECTION_ORDER),
}

# Normalized radial layout. R = 1 is the outer functional radius.
LOGO_RADIUS = 0.20
INNER_SEPARATOR_OUTER = 0.22
CLOCK_INNER = 0.22
CLOCK_OUTER = 0.255
HEADER_RINGS: tuple[tuple[float, float], ...] = (
    (0.26, 0.28),
    (0.285, 0.305),
    (0.31, 0.33),
)
# Protocol Draft 0.6: a fourth BCH copy in the stable radial gap between the
# inner header cluster and the data field. It is farther from central marks
# without entering the guard's perspective-sensitive band.
OUTER_HEADER_RING: tuple[float, float] = (0.345, 0.365)
ANCHOR_INNER = 0.93
ANCHOR_OUTER = 0.97
DATA_INNER = 0.38
DATA_OUTER = 0.91
CONSTANT_COLUMNS_DATA_INNER = 0.41
CONSTANT_COLUMNS_BY_GEOMETRY: dict[int, int] = {
    0: 216,
    1: 160,
    2: 168,
    3: 168,
    4: 168,
    5: 188,
    6: 266,
}
OUTER_SEPARATOR_OUTER = 0.93
GUARD_INNER = 0.93
GUARD_OUTER = 0.97
QUIET_ZONE_OUTER = 1.05

CLOCK_SLOTS = 64
CLOCK_PHASE_SLOT = 0
CLOCK_ORDER = 6
CLOCK_TAP_MASK = 0b100001  # x^6 + x^5 + 1 under the RadialCode left-shift convention.
CLOCK_POLYNOMIAL = 0b1100001  # Leading term included.
CLOCK_INITIAL_STATE = 0b111111
ANCHOR_SLOTS: tuple[int, ...] = (0, 19, 46, 81)
HEADER_PHYSICAL_SLOTS = 64
HEADER_CODE_BITS = 63
HEADER_DATA_BITS = 45

DATA_RESERVED_CELLS = 24
COLOR_REFERENCE_REPETITIONS = 4
ROUND_SECTOR_MULTIPLE = 8
MIN_RING_SECTORS = 24

# Registered renderer palettes. Observed reference cells remain the decoder truth;
# the palette id provides a stable rendering/interoperability contract.
PALETTES: dict[int, tuple[str, ...]] = {
    0: ("#111111", "#00A6D6", "#D81B60", "#F0C808"),  # C4-PRINT-1
    1: ("#111111", "#4CC9F0", "#F72585", "#A7C957"),  # C4-NOCTURNE-1
    2: ("#111111", "#2A9D8F", "#E76F51", "#FFD60A"),  # C4-TERRA-1
    3: ("#111111", "#219EBC", "#FF4D6D", "#80ED99"),  # C4-SIGNAL-1
}

PALETTE_NAMES: dict[int, str] = {
    0: "C4-PRINT-1",
    1: "C4-NOCTURNE-1",
    2: "C4-TERRA-1",
    3: "C4-SIGNAL-1",
}

MONO_PALETTE: tuple[str, str] = ("#FFFFFF", "#111111")
BOOTSTRAP_DARK = "#111111"
BOOTSTRAP_LIGHT = "#FFFFFF"
DEFAULT_BACKGROUND = "#FFFFFF"

# Rendering defaults. Fill values are fractions of the logical cell dimensions.
DEFAULT_RADIAL_FILL = 0.78
DEFAULT_ANGULAR_FILL = 0.78
DEFAULT_DPI = 300
PROVISIONAL_MIN_PRINT_PITCH_MM = 0.50
