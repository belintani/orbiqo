"""Payload framing, optional compression and CRC32C integrity."""

from __future__ import annotations

from dataclasses import dataclass
import zlib

from .constants import CompressionType, PayloadType

FRAME_VERSION = 1
FRAME_FIXED_OVERHEAD = 8  # control + original_length_u24 + CRC32C
MAX_FRAME_ORIGINAL_LENGTH = (1 << 24) - 1
_CRC32C_POLY_REFLECTED = 0x82F63B78


class FrameError(ValueError):
    """Raised when a decoded frame is malformed or fails integrity checks."""


@dataclass(frozen=True, slots=True)
class PayloadFrame:
    payload: bytes
    payload_type: PayloadType
    compression: CompressionType
    original_length: int
    encoded_bytes: bytes



def _crc32c_table() -> tuple[int, ...]:
    table: list[int] = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ (_CRC32C_POLY_REFLECTED if crc & 1 else 0)
        table.append(crc & 0xFFFFFFFF)
    return tuple(table)


_CRC32C_TABLE = _crc32c_table()


def crc32c(data: bytes, initial: int = 0) -> int:
    crc = initial ^ 0xFFFFFFFF
    for byte in data:
        crc = _CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def _control_byte(payload_type: PayloadType, compression: CompressionType, flags: int = 0) -> int:
    if not 0 <= flags <= 0b11:
        raise FrameError("frame flags must fit in two bits")
    return (
        ((FRAME_VERSION & 0b11) << 6)
        | ((int(payload_type) & 0b11) << 4)
        | ((int(compression) & 0b11) << 2)
        | flags
    )


def _normalize_payload(payload: bytes | str, payload_type: PayloadType | None) -> tuple[bytes, PayloadType]:
    if isinstance(payload, str):
        if payload_type is None:
            payload_type = PayloadType.UTF8
        if payload_type not in (PayloadType.UTF8, PayloadType.URL):
            raise FrameError("string payload requires UTF8 or URL payload type")
        return payload.encode("utf-8"), payload_type
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes or str")
    return payload, payload_type or PayloadType.BINARY


def encode_frame(
    payload: bytes | str,
    *,
    payload_type: PayloadType | None = None,
    compression: CompressionType | str = "auto",
    flags: int = 0,
) -> PayloadFrame:
    raw, payload_type = _normalize_payload(payload, payload_type)
    if len(raw) > MAX_FRAME_ORIGINAL_LENGTH:
        raise FrameError("payload exceeds the 24-bit original length field")

    if compression == "auto":
        compressed = zlib.compress(raw, level=9)
        if len(compressed) < len(raw):
            stored = compressed
            selected = CompressionType.DEFLATE
        else:
            stored = raw
            selected = CompressionType.NONE
    else:
        if isinstance(compression, str):
            names = {"none": CompressionType.NONE, "deflate": CompressionType.DEFLATE}
            try:
                selected = names[compression.lower()]
            except KeyError as exc:
                raise FrameError(f"unsupported compression: {compression}") from exc
        else:
            try:
                selected = CompressionType(compression)
            except (TypeError, ValueError) as exc:
                raise FrameError(f"unsupported compression: {compression}") from exc
        stored = zlib.compress(raw, level=9) if selected is CompressionType.DEFLATE else raw

    prefix = bytes([_control_byte(payload_type, selected, flags)]) + len(raw).to_bytes(3, "big")
    body = prefix + stored
    checksum = crc32c(body).to_bytes(4, "big")
    encoded = body + checksum
    return PayloadFrame(
        payload=raw,
        payload_type=payload_type,
        compression=selected,
        original_length=len(raw),
        encoded_bytes=encoded,
    )


def decode_frame(encoded: bytes) -> PayloadFrame:
    if len(encoded) < FRAME_FIXED_OVERHEAD:
        raise FrameError("frame is shorter than the fixed overhead")

    body = encoded[:-4]
    expected_crc = int.from_bytes(encoded[-4:], "big")
    actual_crc = crc32c(body)
    if actual_crc != expected_crc:
        raise FrameError(f"CRC32C mismatch: expected 0x{expected_crc:08X}, got 0x{actual_crc:08X}")

    control = body[0]
    version = (control >> 6) & 0b11
    if version != FRAME_VERSION:
        raise FrameError(f"unsupported frame version: {version}")
    try:
        payload_type = PayloadType((control >> 4) & 0b11)
        compression = CompressionType((control >> 2) & 0b11)
    except ValueError as exc:
        raise FrameError("frame contains an unsupported enum value") from exc

    original_length = int.from_bytes(body[1:4], "big")
    stored = body[4:]
    if compression is CompressionType.NONE:
        payload = stored
    elif compression is CompressionType.DEFLATE:
        try:
            payload = zlib.decompress(stored)
        except zlib.error as exc:
            raise FrameError("DEFLATE payload is malformed") from exc
    else:  # pragma: no cover - guarded by enum conversion
        raise FrameError("unsupported compression")

    if len(payload) != original_length:
        raise FrameError(f"original length mismatch: expected {original_length}, got {len(payload)}")
    if payload_type in (PayloadType.UTF8, PayloadType.URL):
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrameError("text payload is not valid UTF-8") from exc

    return PayloadFrame(
        payload=payload,
        payload_type=payload_type,
        compression=compression,
        original_length=original_length,
        encoded_bytes=encoded,
    )
