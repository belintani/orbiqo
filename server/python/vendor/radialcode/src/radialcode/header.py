"""Bootstrap header layout and BCH integration."""

from __future__ import annotations

from dataclasses import dataclass

from . import bch
from .constants import (
    FORMAT_MAGIC,
    FORMAT_VERSION,
    GEOMETRY_IDS_BY_FORMAT,
    SUPPORTED_FORMAT_VERSIONS,
    GEOMETRY_VERSIONS,
    PALETTES,
    Alphabet,
    EccLevel,
    EccScheme,
)


class HeaderError(ValueError):
    """Raised when a decoded header is structurally invalid."""


@dataclass(frozen=True, slots=True)
class RadialHeader:
    geometry_version: int
    alphabet: Alphabet = Alphabet.COLOR4
    palette_id: int = 0
    ecc_scheme: EccScheme = EccScheme.RS_GF256
    ecc_level: EccLevel = EccLevel.BALANCED
    mask_id: int = 0
    encoded_payload_length: int = 0
    flags: int = 0
    format_version: int = FORMAT_VERSION
    magic: int = FORMAT_MAGIC

    def validate(self) -> None:
        if self.magic != FORMAT_MAGIC:
            raise HeaderError(f"unexpected format magic: 0x{self.magic:02X}")
        if self.format_version not in SUPPORTED_FORMAT_VERSIONS:
            raise HeaderError(f"unsupported format version: {self.format_version}")
        if self.geometry_version not in GEOMETRY_IDS_BY_FORMAT[self.format_version]:
            raise HeaderError(
                f"unsupported geometry version {self.geometry_version} for format {self.format_version}"
            )
        if self.alphabet is Alphabet.COLOR8:
            raise HeaderError("COLOR8 is reserved in Protocol Draft 0.5")
        if not 0 <= self.palette_id <= 7:
            raise HeaderError("palette_id must fit in 3 bits")
        if self.alphabet is Alphabet.COLOR4 and self.palette_id not in PALETTES:
            raise HeaderError(f"unknown COLOR4 palette: {self.palette_id}")
        if self.ecc_scheme is not EccScheme.RS_GF256:
            raise HeaderError("unsupported ECC scheme")
        if not 0 <= self.mask_id <= 7:
            raise HeaderError("mask_id must fit in 3 bits")
        if not 0 <= self.encoded_payload_length <= 0xFFFF:
            raise HeaderError("encoded_payload_length must fit in 16 bits")
        if not 0 <= self.flags <= 0b111:
            raise HeaderError("flags must fit in 3 bits")

    def to_data_int(self) -> int:
        self.validate()
        fields = (
            (self.magic, 8),
            (self.format_version, 3),
            (self.geometry_version, 3),
            (int(self.alphabet), 2),
            (self.palette_id, 3),
            (int(self.ecc_scheme), 2),
            (int(self.ecc_level), 2),
            (self.mask_id, 3),
            (self.encoded_payload_length, 16),
            (self.flags, 3),
        )
        value = 0
        width = 0
        for field, bits in fields:
            if field < 0 or field >= (1 << bits):
                raise HeaderError(f"field {field} does not fit in {bits} bits")
            value = (value << bits) | field
            width += bits
        if width != bch.BCH_K:
            raise AssertionError(f"header width must be {bch.BCH_K}, got {width}")
        return value

    def encode_codeword(self) -> int:
        return bch.encode(self.to_data_int())

    def codeword_bits(self) -> tuple[int, ...]:
        return bch.int_to_bits(self.encode_codeword(), bch.BCH_N)

    @classmethod
    def from_data_int(cls, value: int) -> "RadialHeader":
        if value < 0 or value >= (1 << bch.BCH_K):
            raise HeaderError("header data must fit in 45 bits")

        widths = (3, 16, 3, 2, 2, 3, 2, 3, 3, 8)
        extracted: list[int] = []
        remaining = value
        for width in widths:
            extracted.append(remaining & ((1 << width) - 1))
            remaining >>= width
        (
            flags,
            payload_length,
            mask_id,
            ecc_level,
            ecc_scheme,
            palette_id,
            alphabet,
            geometry_version,
            format_version,
            magic,
        ) = extracted
        if remaining:
            raise HeaderError("unexpected high bits in header")

        try:
            header = cls(
                magic=magic,
                format_version=format_version,
                geometry_version=geometry_version,
                alphabet=Alphabet(alphabet),
                palette_id=palette_id,
                ecc_scheme=EccScheme(ecc_scheme),
                ecc_level=EccLevel(ecc_level),
                mask_id=mask_id,
                encoded_payload_length=payload_length,
                flags=flags,
            )
        except ValueError as exc:
            raise HeaderError("header contains an unknown enum value") from exc
        header.validate()
        return header

    @classmethod
    def decode_codeword(cls, codeword: int) -> tuple["RadialHeader", int]:
        data, _, corrected_bits = bch.decode(codeword)
        return cls.from_data_int(data), corrected_bits
