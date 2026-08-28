#!/usr/bin/env python3
"""Bounded JSON bridge to the local RadialCode reference implementation."""

from __future__ import annotations

import base64
from dataclasses import asdict
import ipaddress
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from math import ceil, pi
from time import perf_counter
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

MAX_REQUEST_BYTES = 12 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_PIXELS = 16_000_000
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_CENTER_IMAGE_URL_LENGTH = 2_048
MAX_CENTER_IMAGE_BYTES = 2 * 1024 * 1024
MAX_CENTER_IMAGE_DIMENSION = 2_048
MAX_CENTER_IMAGE_PIXELS = 4_000_000
MAX_CENTER_IMAGE_REDIRECTS = 3
CENTER_IMAGE_OUTPUT_PX = 256
ALLOWED_CENTER_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}


def _reference_root() -> Path:
    configured = os.environ.get("ORBIQO_RADIALCODE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "radialcode"


REFERENCE_ROOT = _reference_root()
REFERENCE_SRC = REFERENCE_ROOT / "src"
if not REFERENCE_SRC.is_dir():
    raise RuntimeError(f"RadialCode reference source not found at {REFERENCE_SRC}")
sys.path.insert(0, str(REFERENCE_SRC))

from PIL import Image, ImageColor, UnidentifiedImageError  # noqa: E402
import radialcode  # noqa: E402
from radialcode.bootstrap import anchor_patterns, clock_track_bits, header_physical_bits  # noqa: E402
from radialcode.capacity import capacity_for, choose_geometry  # noqa: E402
from radialcode.constants import (  # noqa: E402
    CONSTANT_COLUMNS_BY_GEOMETRY,
    CONSTANT_COLUMNS_DATA_INNER,
    ANCHOR_INNER,
    ANCHOR_OUTER,
    BOOTSTRAP_DARK,
    CLOCK_INNER,
    CLOCK_OUTER,
    CLOCK_SLOTS,
    FORMAT_VERSION,
    GEOMETRY_SELECTION_ORDER,
    GEOMETRY_VERSIONS,
    GUARD_INNER,
    GUARD_OUTER,
    HEADER_PHYSICAL_SLOTS,
    HEADER_RINGS,
    LOGO_RADIUS,
    OUTER_HEADER_RING,
    PALETTES,
    PALETTE_NAMES,
    QUIET_ZONE_OUTER,
    SUPPORTED_FORMAT_VERSIONS,
    Alphabet,
    EccLevel,
    PayloadType,
)
from radialcode.decoder import DecodeError, decode_canonical  # noqa: E402
from radialcode.encoder import encode  # noqa: E402
from radialcode.framing import encode_frame  # noqa: E402
from radialcode.renderer import SVG_CANVAS, SVG_CENTER, SVG_R, RenderOptions, render_png_fast, render_svg  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import zxingcpp  # noqa: E402
from benchmark.run_normalized_comparison import JabAdapter, ZxingAdapter, normalize_fixed  # noqa: E402


ECC_NAMES = {
    "fast": EccLevel.FAST,
    "balanced": EccLevel.BALANCED,
    "robust": EccLevel.ROBUST,
    "extreme": EccLevel.EXTREME,
}
PAYLOAD_NAMES = {
    "binary": PayloadType.BINARY,
    "text": PayloadType.UTF8,
    "url": PayloadType.URL,
}
ALPHABET_NAMES = {"color4": Alphabet.COLOR4, "mono2": Alphabet.MONO2}
VISUAL_STYLES = {
    "reference": {"angular_fill": 0.88, "radial_fill": 0.72},
    "pulse": {"angular_fill": 0.82, "radial_fill": 0.80},
}
VISUAL_IDENTITIES = {
    "reference": {
        "name": "Reference",
        "description": "Technical baseline with wider radial breathing room.",
        "tone": "Neutral / technical",
        "palette_id": 0,
        "visual_style": "reference",
        "recommended_for": "Inspection and engineering comparison",
    },
    "pulse": {
        "name": "Pulse",
        "description": "The original Orbiqo signature: bright, energetic and balanced.",
        "tone": "Signature / vivid",
        "palette_id": 0,
        "visual_style": "pulse",
        "recommended_for": "General use and product surfaces",
    },
    "nocturne": {
        "name": "Nocturne",
        "description": "Deep blue, electric pink and lime with a cooler digital character.",
        "tone": "Digital / nocturnal",
        "palette_id": 1,
        "visual_style": "pulse",
        "recommended_for": "Technology and entertainment identities",
    },
    "terra": {
        "name": "Terra",
        "description": "Teal, mineral orange and warm yellow with an editorial character.",
        "tone": "Warm / editorial",
        "palette_id": 2,
        "visual_style": "pulse",
        "recommended_for": "Hospitality, culture and physical products",
    },
    "signal": {
        "name": "Signal",
        "description": "Blue, coral and mint tuned for a crisp contemporary presence.",
        "tone": "Clear / contemporary",
        "palette_id": 3,
        "visual_style": "pulse",
        "recommended_for": "Services, wayfinding and communications",
    },
}

TAU = 2.0 * pi
NATIVE_RENDERER_MAGIC = "ORBIQO_RASTER_V1"
NATIVE_RENDERER_TIMEOUT_SECONDS = 15
NATIVE_RENDERER_MAX_OUTPUT_BYTES = 12 * 1024 * 1024


class BridgeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _rgb(value: str) -> tuple[int, int, int]:
    color = ImageColor.getrgb(value)
    if len(color) < 3:
        raise ValueError(f"unable to parse RGB color: {value}")
    return int(color[0]), int(color[1]), int(color[2])


def _native_renderer_path() -> Path:
    configured = os.environ.get("ORBIQO_NATIVE_RENDERER_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "server" / "python" / "native" / "orbiqo_renderer"


def _native_renderer_input(symbol: Any, *, dpi: int, options: RenderOptions) -> tuple[bytes, int]:
    """Return a bounded, line-oriented V1 draw list for the native core renderer."""
    supersample = 3 if symbol.geometry.version.data_rings <= 4 else 2 if symbol.geometry.version.number >= 3 else 1
    total_mm = symbol.diameter_mm * QUIET_ZONE_OUTER
    output_pixels = max(1, int(ceil(total_mm / 25.4 * dpi)))
    pixels = output_pixels * supersample
    scale = pixels / SVG_CANVAS
    center = SVG_CENTER * scale
    functional_radius = SVG_R * scale
    background = _rgb(options.background)
    dark = _rgb(BOOTSTRAP_DARK)
    palette = [_rgb(color) for color in (PALETTES[symbol.palette_id] if symbol.alphabet is not Alphabet.MONO2 else ("#ffffff", BOOTSTRAP_DARK))]
    lines = [
        NATIVE_RENDERER_MAGIC,
        f"CANVAS {pixels} {output_pixels} {supersample} {center:.8f} {background[0]} {background[1]} {background[2]}",
        f"DARK {dark[0]} {dark[1]} {dark[2]}",
        f"GUARD {((GUARD_INNER + GUARD_OUTER) / 2.0) * functional_radius:.8f} {(GUARD_OUTER - GUARD_INNER) * functional_radius:.8f}",
        "PALETTE " + str(len(palette)) + " " + " ".join(f"{red} {green} {blue}" for red, green, blue in palette),
    ]

    clock_radius = ((CLOCK_INNER + CLOCK_OUTER) / 2.0) * functional_radius
    clock_width = max(1, int(round((CLOCK_OUTER - CLOCK_INNER) * functional_radius * 0.90)))
    clock_span = TAU / CLOCK_SLOTS
    for slot, bit in enumerate(clock_track_bits()):
        if bit:
            gutter = clock_span * 0.12
            lines.append(f"ARC {clock_radius:.8f} {clock_width} {slot * clock_span + gutter:.10f} {(slot + 1) * clock_span - gutter:.10f} {dark[0]} {dark[1]} {dark[2]} 0")

    header_rings = HEADER_RINGS + ((OUTER_HEADER_RING,) if symbol.header.format_version >= 5 else ())
    for copy_index, (r_inner, r_outer) in enumerate(header_rings):
        radius = ((r_inner + r_outer) / 2.0) * functional_radius
        width = max(1, int(round((r_outer - r_inner) * functional_radius * 0.78)))
        span = TAU / HEADER_PHYSICAL_SLOTS
        for slot, bit in enumerate(header_physical_bits(symbol.header, copy_index)):
            if bit:
                gutter = span * 0.13
                lines.append(f"ARC {radius:.8f} {width} {slot * span + gutter:.10f} {(slot + 1) * span - gutter:.10f} {dark[0]} {dark[1]} {dark[2]} 0")

    for anchor in anchor_patterns():
        anchor_center = anchor.center_slot * TAU / 128.0
        half_span = anchor.width_slots * TAU / 128.0 * 0.38
        anchor_radius = ((ANCHOR_INNER + ANCHOR_OUTER) / 2.0) * functional_radius
        anchor_width = max(1, int(round((ANCHOR_OUTER - ANCHOR_INNER) * functional_radius * 0.64)))
        lines.append(f"ARC {anchor_radius:.8f} {anchor_width} {anchor_center - half_span:.10f} {anchor_center + half_span:.10f} {background[0]} {background[1]} {background[2]} 1")

    cells_by_ring: dict[int, list[Any]] = {}
    for cell in symbol.geometry.cells:
        cells_by_ring.setdefault(cell.address.ring, []).append(cell)
    for ring_index in sorted(cells_by_ring):
        cells = cells_by_ring[ring_index]
        first = cells[0]
        half_width = (first.r_outer - first.r_inner) * options.radial_fill * functional_radius / 2.0
        inner = first.r_center * functional_radius - half_width
        outer = first.r_center * functional_radius + half_width
        states = "".join(str(symbol.cell_states[cell.address]) for cell in cells)
        lines.append(f"DATA {inner:.8f} {outer:.8f} {len(cells)} {options.angular_fill:.8f} {first.theta_start:.10f} {states}")

    logo_radius = LOGO_RADIUS * functional_radius * 0.92
    logo_width = max(1, int(round(functional_radius * 0.008)))
    lines.append(f"CENTER {logo_radius:.8f} {logo_width}")
    lines.append("END")
    return ("\n".join(lines) + "\n").encode("ascii"), output_pixels


def _render_png_native(symbol: Any, *, dpi: int, options: RenderOptions) -> bytes:
    if options.center_image_png is not None or options.center_text:
        raise BridgeError("NATIVE_RENDERER_UNSUPPORTED_OPTION", "native experimental renderer currently requires an empty center")
    executable = _native_renderer_path()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise BridgeError("NATIVE_RENDERER_UNAVAILABLE", f"native renderer executable not found at {executable}")
    request, output_pixels = _native_renderer_input(symbol, dpi=dpi, options=options)
    try:
        completed = subprocess.run(
            [str(executable)],
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=NATIVE_RENDERER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeError("NATIVE_RENDERER_TIMEOUT", "native renderer exceeded its time limit") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:200]
        raise BridgeError("NATIVE_RENDERER_FAILED", f"native renderer failed: {detail or completed.returncode}")
    if len(completed.stdout) == 0 or len(completed.stdout) > NATIVE_RENDERER_MAX_OUTPUT_BYTES:
        raise BridgeError("NATIVE_RENDERER_FAILED", "native renderer returned an invalid output size")
    try:
        with Image.open(BytesIO(completed.stdout)) as rendered:
            rendered.load()
            if rendered.format != "PNG" or rendered.size != (output_pixels, output_pixels):
                raise BridgeError("NATIVE_RENDERER_FAILED", "native renderer returned an unexpected PNG geometry")
    except BridgeError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise BridgeError("NATIVE_RENDERER_FAILED", "native renderer output is not a readable PNG") from exc
    return completed.stdout


def _render_png(symbol: Any, *, dpi: int, options: RenderOptions, backend: str) -> tuple[bytes, str, str | None]:
    if backend == "reference":
        return render_png_fast(symbol, dpi=dpi, options=options), "python-reference", None
    if backend != "native-experimental":
        raise BridgeError("INVALID_INPUT", "raster_backend must be reference or native-experimental")
    try:
        return _render_png_native(symbol, dpi=dpi, options=options), "cpp-native-experimental", None
    except BridgeError as exc:
        if exc.code != "NATIVE_RENDERER_UNSUPPORTED_OPTION":
            raise
        return render_png_fast(symbol, dpi=dpi, options=options), "python-reference-fallback", str(exc)


def _decode_b64(value: object, *, field: str, maximum: int) -> bytes:
    if not isinstance(value, str):
        raise BridgeError("INVALID_INPUT", f"{field} must be base64 text")
    try:
        decoded = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise BridgeError("INVALID_BASE64", f"{field} is not valid base64") from exc
    if len(decoded) > maximum:
        raise BridgeError("INPUT_TOO_LARGE", f"{field} exceeds {maximum} bytes")
    return decoded


def _enum(mapping: dict[str, Any], value: object, field: str) -> Any:
    if not isinstance(value, str) or value not in mapping:
        raise BridgeError("INVALID_INPUT", f"unsupported {field}: {value!r}")
    return mapping[value]


def _geometry(value: object) -> int | str:
    if value in ("auto", "micro-1", "micro-2", "micro-4", "small", "medium", "large", "xl"):
        return str(value)
    if isinstance(value, int) and value in GEOMETRY_VERSIONS:
        return value
    raise BridgeError("INVALID_INPUT", "geometry must be auto, micro-1, micro-2, micro-4, small, medium, large, xl, or an ID from 0–6")


def _payload(request: dict[str, Any]) -> tuple[bytes | str, PayloadType]:
    payload_type = _enum(PAYLOAD_NAMES, request.get("payload_type"), "payload_type")
    if payload_type is PayloadType.BINARY:
        payload = _decode_b64(request.get("payload_base64"), field="payload_base64", maximum=MAX_PAYLOAD_BYTES)
    else:
        value = request.get("text")
        if not isinstance(value, str):
            raise BridgeError("INVALID_INPUT", "text must be a string")
        payload = value
        if len(value.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise BridgeError("INPUT_TOO_LARGE", "text payload is too large")
    return payload, payload_type


def _require_public_https(url: str) -> tuple[str, str]:
    if len(url) > MAX_CENTER_IMAGE_URL_LENGTH:
        raise BridgeError("CENTER_IMAGE_URL_TOO_LONG", "center_image_url exceeds 2048 characters")
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise BridgeError("CENTER_IMAGE_INVALID_URL", "center_image_url must be a public HTTPS URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise BridgeError("CENTER_IMAGE_INVALID_URL", "center_image_url contains an invalid port") from exc
    if parsed.username or parsed.password or port not in (None, 443):
        raise BridgeError("CENTER_IMAGE_INVALID_URL", "center_image_url must not include credentials or a custom port")
    host = parsed.hostname.rstrip(".").lower()
    try:
        resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise BridgeError("CENTER_IMAGE_UNREACHABLE", "center image host could not be resolved") from exc
    for _family, _type, _protocol, _canonname, sockaddr in resolved:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise BridgeError("CENTER_IMAGE_UNREACHABLE", "center image host resolved to an invalid address") from exc
        if not address.is_global:
            raise BridgeError("CENTER_IMAGE_FORBIDDEN_HOST", "center image URL must resolve to a public address")
    return url, host


def _normalize_center_image(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.load()
            if opened.format not in ALLOWED_CENTER_IMAGE_FORMATS:
                raise BridgeError("CENTER_IMAGE_INVALID_FORMAT", "center image must be PNG, JPEG, or WebP")
            if opened.width > MAX_CENTER_IMAGE_DIMENSION or opened.height > MAX_CENTER_IMAGE_DIMENSION:
                raise BridgeError("CENTER_IMAGE_TOO_LARGE", "center image dimensions exceed 2048 px")
            if opened.width * opened.height > MAX_CENTER_IMAGE_PIXELS:
                raise BridgeError("CENTER_IMAGE_TOO_LARGE", "center image exceeds four million pixels")
            side = min(opened.width, opened.height)
            left = (opened.width - side) // 2
            top = (opened.height - side) // 2
            normalized = opened.convert("RGBA").crop((left, top, left + side, top + side))
            normalized = normalized.resize((CENTER_IMAGE_OUTPUT_PX, CENTER_IMAGE_OUTPUT_PX), Image.Resampling.LANCZOS)
    except BridgeError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BridgeError("CENTER_IMAGE_INVALID_FORMAT", "center image is not a supported readable image") from exc
    output = BytesIO()
    normalized.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _fetch_center_image(value: object) -> tuple[bytes | None, str | None]:
    if value is None or value == "":
        return None, None
    if not isinstance(value, str):
        raise BridgeError("CENTER_IMAGE_INVALID_URL", "center_image_url must be a string")
    current, origin_host = _require_public_https(value)
    response: requests.Response | None = None
    try:
        for redirect_count in range(MAX_CENTER_IMAGE_REDIRECTS + 1):
            current, _host = _require_public_https(current)
            try:
                response = requests.get(
                    current,
                    allow_redirects=False,
                    stream=True,
                    timeout=(3, 7),
                    headers={"Accept": "image/png,image/jpeg,image/webp", "User-Agent": "Orbiqo-CenterImage/1.0"},
                )
            except requests.RequestException as exc:
                raise BridgeError("CENTER_IMAGE_UNREACHABLE", "center image could not be fetched") from exc
            if response.is_redirect:
                location = response.headers.get("Location")
                response.close()
                response = None
                if not location or redirect_count == MAX_CENTER_IMAGE_REDIRECTS:
                    raise BridgeError("CENTER_IMAGE_REDIRECT_LIMIT", "center image exceeded the redirect limit")
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                raise BridgeError("CENTER_IMAGE_FETCH_FAILED", "center image server did not return HTTP 200")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_CENTER_IMAGE_BYTES:
                    raise BridgeError("CENTER_IMAGE_TOO_LARGE", "center image exceeds two MiB")
            return _normalize_center_image(bytes(data)), origin_host
    finally:
        if response is not None:
            response.close()
    raise BridgeError("CENTER_IMAGE_REDIRECT_LIMIT", "center image exceeded the redirect limit")


def _generate(request: dict[str, Any]) -> dict[str, Any]:
    payload, payload_type = _payload(request)
    sizing_mode = request.get("sizing_mode", "manual")
    if sizing_mode not in ("auto", "manual"):
        raise BridgeError("INVALID_INPUT", "sizing_mode must be auto or manual")
    requested_geometry = _geometry(request.get("geometry", "auto"))
    if sizing_mode == "auto":
        requested_geometry = "auto"
        diameter: float | None = None
    else:
        if requested_geometry == "auto":
            raise BridgeError("INVALID_INPUT", "manual sizing requires a fixed geometry")
        diameter = float(request.get("diameter_mm", 30.0))
        if not 10.0 <= diameter <= 300.0:
            raise BridgeError("INVALID_INPUT", "diameter_mm must be between 10 and 300")
    dpi = int(request.get("dpi", 600))
    if not 72 <= dpi <= 600:
        raise BridgeError("INVALID_INPUT", "dpi must be between 72 and 600")
    center_mark = request.get("center_mark")
    if center_mark is not None and (not isinstance(center_mark, str) or len(center_mark) > 8):
        raise BridgeError("INVALID_INPUT", "center_mark must contain at most 8 characters")
    identity_id = request.get("identity_id")
    if identity_id is None:
        legacy_style = request.get("visual_style", "pulse")
        identity_id = legacy_style if legacy_style in ("reference", "pulse") else "pulse"
    if not isinstance(identity_id, str) or identity_id not in VISUAL_IDENTITIES:
        raise BridgeError("INVALID_INPUT", f"unsupported identity_id: {identity_id!r}")
    identity = VISUAL_IDENTITIES[identity_id]
    visual_style = str(identity["visual_style"])
    palette_id = int(identity["palette_id"])
    center_image_png, center_image_host = _fetch_center_image(request.get("center_image_url"))

    started = perf_counter()
    try:
        symbol = encode(
            payload,
            payload_type=payload_type,
            geometry=requested_geometry,
            diameter_mm=diameter,
            alphabet=_enum(ALPHABET_NAMES, request.get("alphabet", "color4"), "alphabet"),
            ecc_level=_enum(ECC_NAMES, request.get("ecc", "balanced"), "ecc"),
            palette_id=palette_id,
            compression=str(request.get("compression", "auto")),
        )
    except ValueError as exc:
        if "frame requires" in str(exc):
            raise BridgeError("CAPACITY_EXCEEDED", str(exc)) from exc
        raise
    style = VISUAL_STYLES[visual_style]
    options = RenderOptions(
        center_text=center_mark or None,
        center_image_png=center_image_png,
        angular_fill=style["angular_fill"],
        radial_fill=style["radial_fill"],
    )
    svg = render_svg(symbol, options)
    raster_backend = request.get("raster_backend", "reference")
    if not isinstance(raster_backend, str):
        raise BridgeError("INVALID_INPUT", "raster_backend must be reference or native-experimental")
    png, raster_renderer, native_fallback_reason = _render_png(
        symbol,
        dpi=dpi,
        options=options,
        backend=raster_backend,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0
    capacity = capacity_for(
        symbol.geometry.version.number,
        symbol.alphabet,
        symbol.ecc_level,
        format_version=symbol.header.format_version,
    )
    return {
        "svg": svg,
        "png_base64": base64.b64encode(png).decode("ascii"),
        "center_image_preview_base64": base64.b64encode(center_image_png).decode("ascii") if center_image_png is not None else None,
        "metadata": {
            "format_version": symbol.header.format_version,
            "geometry_version": symbol.geometry.version.number,
            "geometry_name": symbol.geometry.version.name,
            "layout_name": "constant-columns" if symbol.header.format_version == FORMAT_VERSION else "legacy-radial",
            "columns": symbol.geometry.sector_counts[0],
            "data_inner": symbol.geometry.data_inner,
            "diameter_mm": symbol.diameter_mm,
            "recommended_diameter_mm": symbol.geometry.version.recommended_diameter_mm,
            "sizing_mode": sizing_mode,
            "requested_geometry": requested_geometry,
            "selection_reason": (
                "smallest geometry that fits the encoded frame at the selected ECC"
                if sizing_mode == "auto"
                else "manual geometry and diameter override"
            ),
            "physical_pitch_mm": symbol.diagnostics.physical_pitch_mm,
            "print_pitch_warning": symbol.diagnostics.print_pitch_warning,
            "alphabet": symbol.alphabet.name,
            "ecc_level": symbol.ecc_level.name,
            "payload_type": symbol.frame.payload_type.name,
            "payload_bytes": len(symbol.payload),
            "frame_bytes": len(symbol.frame.encoded_bytes),
            "mask_id": symbol.header.mask_id,
            "palette_id": symbol.header.palette_id,
            "palette_name": PALETTE_NAMES[symbol.header.palette_id],
            "palette_colors": list(PALETTES[symbol.header.palette_id]),
            "maximum_uncompressed_payload_bytes": capacity.maximum_uncompressed_payload_bytes,
            "generation_time_ms": elapsed_ms,
            "raster_backend_requested": raster_backend,
            "raster_renderer": raster_renderer,
            "native_fallback_reason": native_fallback_reason,
            "attribution": symbol.attribution,
            "visual_style": visual_style,
            "identity_id": identity_id,
            "identity_name": identity["name"],
            "center_image_applied": center_image_png is not None,
            "center_image_host": center_image_host,
        },
    }


def _identities() -> dict[str, Any]:
    rows = []
    for identity_id, identity in VISUAL_IDENTITIES.items():
        palette_id = int(identity["palette_id"])
        style = VISUAL_STYLES[str(identity["visual_style"])]
        rows.append(
            {
                "id": identity_id,
                **identity,
                "palette_name": PALETTE_NAMES[palette_id],
                "colors": list(PALETTES[palette_id]),
                "angular_fill": style["angular_fill"],
                "radial_fill": style["radial_fill"],
                "validation_status": "digital-validated",
                "format_version": FORMAT_VERSION,
            }
        )
    return {
        "default_identity_id": "pulse",
        "custom_colors_supported": False,
        "identities": rows,
    }


def _recommend_sizing(request: dict[str, Any]) -> dict[str, Any]:
    payload, payload_type = _payload(request)
    alphabet = _enum(ALPHABET_NAMES, request.get("alphabet", "color4"), "alphabet")
    ecc = _enum(ECC_NAMES, request.get("ecc", "balanced"), "ecc")
    frame = encode_frame(
        payload,
        payload_type=payload_type,
        compression=str(request.get("compression", "auto")),
    )
    try:
        version = choose_geometry(
            len(frame.encoded_bytes),
            alphabet=alphabet,
            ecc_level=ecc,
            format_version=FORMAT_VERSION,
        )
    except ValueError as exc:
        raise BridgeError("CAPACITY_EXCEEDED", str(exc)) from exc
    geometry = GEOMETRY_VERSIONS[version]
    capacity = capacity_for(version, alphabet, ecc, format_version=FORMAT_VERSION)
    return {
        "format_version": FORMAT_VERSION,
        "geometry_version": version,
        "geometry_name": geometry.name,
        "recommended_diameter_mm": geometry.recommended_diameter_mm,
        "payload_bytes": len(frame.payload),
        "frame_bytes": len(frame.encoded_bytes),
        "compression": frame.compression.name,
        "maximum_uncompressed_payload_bytes": capacity.maximum_uncompressed_payload_bytes,
        "remaining_nominal_payload_bytes": max(
            0,
            capacity.maximum_uncompressed_payload_bytes - len(frame.payload),
        ),
        "selection_reason": "smallest geometry that fits the encoded frame at the selected ECC",
    }


def _png_base64(image: Image.Image) -> str:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")


def _compare_symbols(request: dict[str, Any]) -> dict[str, Any]:
    payload, _payload_type = _payload(request)
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not payload_bytes:
        raise BridgeError("INVALID_INPUT", "comparison payload must not be empty")

    orbiqo = _generate(
        {
            **request,
            "sizing_mode": "auto",
            "geometry": "auto",
            "alphabet": "color4",
            "ecc": "balanced",
            "dpi": 600,
        }
    )
    orbiqo_native = Image.open(BytesIO(base64.b64decode(orbiqo["png_base64"]))).convert("RGB")
    items: list[dict[str, Any]] = [
        {
            "id": "orbiqo",
            "name": "Orbiqo",
            "png_base64": _png_base64(normalize_fixed(orbiqo_native)),
            "toolchain": f"radialcode {radialcode.__version__}",
            "profile": f"{orbiqo['metadata']['geometry_name']} / COLOR4 / balanced",
            "reported_ecc": "RS(255,191), code rate 74.9%",
            "detail": (
                f"Protocol Draft 0.6 format {orbiqo['metadata']['format_version']}; "
                f"{orbiqo['metadata']['columns']} constant columns"
            ),
            "native_width": orbiqo_native.width,
            "native_height": orbiqo_native.height,
            "geometry": orbiqo["metadata"]["geometry_name"],
            "diameter_mm": orbiqo["metadata"]["diameter_mm"],
        }
    ]

    adapters = [
        ZxingAdapter("qr", zxingcpp.BarcodeFormat.QRCode, "Q"),
        ZxingAdapter("aztec", zxingcpp.BarcodeFormat.Aztec, "25"),
        JabAdapter(),
    ]
    display_names = {"qr": "QR Code", "aztec": "Aztec", "jab": "JAB Code"}
    for adapter in adapters:
        try:
            generated = adapter.generate_normalized(payload_bytes)
        except (ValueError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise BridgeError("COMPARISON_GENERATION_FAILED", f"{adapter.name} generation failed: {exc}") from exc
        items.append(
            {
                "id": adapter.name,
                "name": display_names[adapter.name],
                "png_base64": _png_base64(generated.image),
                "toolchain": adapter.toolchain,
                "profile": generated.profile,
                "reported_ecc": generated.reported_ecc,
                "detail": generated.detail,
                "native_width": int(generated.logical_width),
                "native_height": int(generated.logical_height),
                "geometry": None,
                "diameter_mm": None,
            }
        )

    return {
        "payload_type": str(request.get("payload_type")),
        "payload_bytes": len(payload_bytes),
        "payload_base64": base64.b64encode(payload_bytes).decode("ascii"),
        "canvas_px": 1024,
        "occupied_px": 900,
        "normalization": "Each full symbol, including its required quiet zone, is fitted into the same 900×900 px occupied area on a 1024×1024 px canvas.",
        "ecc_comparability": "Profiles are toolchain-specific and not equivalent: Orbiqo Balanced RS; QR Q; Aztec requested 25%; JAB CLI level 3 (6%).",
        "items": items,
    }


def _preflight_image(image_bytes: bytes) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            image_format = image.format or "UNKNOWN"
    except (UnidentifiedImageError, OSError) as exc:
        raise BridgeError("INVALID_IMAGE", "image could not be identified") from exc
    if width < 64 or height < 64:
        raise BridgeError("IMAGE_TOO_SMALL", "image dimensions must be at least 64×64")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
        raise BridgeError("IMAGE_TOO_LARGE", "image dimensions exceed the configured decode limit")
    return {"width": width, "height": height, "format": image_format}


def _decode(request: dict[str, Any]) -> dict[str, Any]:
    image_bytes = _decode_b64(request.get("image_base64"), field="image_base64", maximum=MAX_IMAGE_BYTES)
    image_info = _preflight_image(image_bytes)
    erasure_threshold = float(request.get("erasure_threshold", 0.55))
    if not 0.0 <= erasure_threshold <= 1.0:
        raise BridgeError("INVALID_INPUT", "erasure_threshold must be between zero and one")

    canonical = bool(request.get("canonical", False))
    rectification = None
    if canonical:
        hint = request.get("geometry_hint")
        decoded = decode_canonical(
            image_bytes,
            geometry_hint=int(hint) if hint is not None else None,
            erasure_threshold=erasure_threshold,
        )
    else:
        from radialcode.vision import decode_image

        detected = decode_image(
            image_bytes,
            output_size=int(request.get("output_size", 1024)),
            erasure_threshold=erasure_threshold,
        )
        decoded = detected.decoded
        rectification = detected.rectification

    diagnostics = decoded.diagnostics
    result: dict[str, Any] = {
        "payload_base64": base64.b64encode(decoded.payload).decode("ascii"),
        "payload_type": decoded.frame.payload_type.name,
        "payload_bytes": len(decoded.payload),
        "format_version": decoded.header.format_version,
        "geometry_version": decoded.header.geometry_version,
        "alphabet": decoded.header.alphabet.name,
        "palette_id": decoded.header.palette_id,
        "palette_name": PALETTE_NAMES[decoded.header.palette_id],
        "ecc_level": decoded.header.ecc_level.name,
        "mask_id": decoded.header.mask_id,
        "image": image_info,
        "diagnostics": {
            "header_corrected_bits": list(diagnostics.header_corrected_bits),
            "corrected_rs_symbols": diagnostics.corrected_rs_symbols,
            "erasure_cells": diagnostics.erasure_cells,
            "erasure_bytes": diagnostics.erasure_bytes,
            "average_confidence": diagnostics.average_confidence,
            "minimum_confidence": diagnostics.minimum_confidence,
            "processing_time_ms": diagnostics.processing_time_ms,
            "color_reference_means": [list(row) for row in diagnostics.color_reference_means],
        },
    }
    if decoded.frame.payload_type in (PayloadType.UTF8, PayloadType.URL):
        result["text"] = decoded.payload.decode("utf-8")
    if rectification is not None:
        result["rectification"] = {
            "axis_ratio": rectification.ellipse.axis_ratio,
            "anchor_widths": list(rectification.anchor_run_lengths),
            "reprojection_error_px": rectification.reprojection_error_px,
            "homography": [list(row) for row in rectification.homography],
        }
    return result


def _capacities(request: dict[str, Any]) -> dict[str, Any]:
    alphabet = _enum(ALPHABET_NAMES, request.get("alphabet", "color4"), "alphabet")
    ecc = _enum(ECC_NAMES, request.get("ecc", "balanced"), "ecc")
    rows = []
    for version in GEOMETRY_SELECTION_ORDER:
        geometry = GEOMETRY_VERSIONS[version]
        capacity = capacity_for(version, alphabet, ecc)
        rows.append(
            {
                "version": version,
                "name": geometry.name,
                "rings": geometry.data_rings,
                "recommended_diameter_mm": geometry.recommended_diameter_mm,
                "layout_name": "constant-columns",
                "columns": CONSTANT_COLUMNS_BY_GEOMETRY[version],
                "data_inner": CONSTANT_COLUMNS_DATA_INNER,
                **asdict(capacity),
            }
        )
    return {"alphabet": alphabet.name, "ecc": ecc.name, "rows": rows}


def _health() -> dict[str, Any]:
    return {
        "product": "Orbiqo Lab",
        "reference_package": "radialcode",
        "reference_version": radialcode.__version__,
        "reference_root": str(REFERENCE_ROOT),
        "supported_format_versions": sorted(SUPPORTED_FORMAT_VERSIONS),
        "default_format_version": max(SUPPORTED_FORMAT_VERSIONS),
        "default_layout": "constant-columns",
        "visual_identity_count": len(VISUAL_IDENTITIES),
    }


def _dispatch(request: dict[str, Any]) -> dict[str, Any]:
    operation = request.get("op")
    if operation == "health":
        return _health()
    if operation == "generate":
        return _generate(request)
    if operation == "decode":
        return _decode(request)
    if operation == "capacity":
        return _capacities(request)
    if operation == "identities":
        return _identities()
    if operation == "recommend_sizing":
        return _recommend_sizing(request)
    if operation == "compare_symbols":
        return _compare_symbols(request)
    raise BridgeError("UNKNOWN_OPERATION", f"unsupported operation: {operation!r}")


def main() -> None:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise BridgeError("INPUT_TOO_LARGE", "request exceeds bridge input limit")
    try:
        request = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BridgeError("INVALID_JSON", "request must be one UTF-8 JSON object") from exc
    if not isinstance(request, dict):
        raise BridgeError("INVALID_JSON", "request root must be an object")
    result = _dispatch(request)
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except BridgeError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": str(exc)}}))
        raise SystemExit(2)
    except (DecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": {"code": "DECODE_FAILED", "message": str(exc)}}))
        raise SystemExit(3)
    except Exception as exc:  # Defensive boundary: never emit a Python traceback as the API response.
        print(json.dumps({"ok": False, "error": {"code": "REFERENCE_FAILURE", "message": str(exc)}}))
        raise SystemExit(4)
