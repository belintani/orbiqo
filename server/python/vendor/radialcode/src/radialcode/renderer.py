"""Deterministic SVG and PNG rendering for RadialCode symbols."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from io import BytesIO
import json
from math import ceil, cos, pi, sin
from pathlib import Path

import cairosvg
from PIL import Image, ImageChops, ImageDraw, ImageFont

from .bootstrap import anchor_patterns, clock_track_bits, header_physical_bits
from .constants import (
    ANCHOR_INNER,
    ANCHOR_OUTER,
    BOOTSTRAP_DARK,
    CLOCK_INNER,
    CLOCK_OUTER,
    CLOCK_SLOTS,
    DEFAULT_ANGULAR_FILL,
    DEFAULT_BACKGROUND,
    DEFAULT_DPI,
    DEFAULT_RADIAL_FILL,
    GUARD_INNER,
    GUARD_OUTER,
    HEADER_PHYSICAL_SLOTS,
    HEADER_RINGS,
    LOGO_RADIUS,
    MONO_PALETTE,
    OUTER_HEADER_RING,
    PALETTES,
    QUIET_ZONE_OUTER,
    Alphabet,
)
from .encoder import EncodedRadialCode
from .geometry import PolarCell, geometry_for_format

TAU = 2.0 * pi
SVG_R = 500.0
SVG_CANVAS = 2.0 * QUIET_ZONE_OUTER * SVG_R
SVG_CENTER = SVG_CANVAS / 2.0


@dataclass(frozen=True, slots=True)
class RenderOptions:
    radial_fill: float = DEFAULT_RADIAL_FILL
    angular_fill: float = DEFAULT_ANGULAR_FILL
    background: str = DEFAULT_BACKGROUND
    center_text: str | None = None
    center_image_png: bytes | None = None
    include_attribution_metadata: bool = True

    def validate(self) -> None:
        if not 0.30 <= self.radial_fill <= 1.0:
            raise ValueError("radial_fill must be between 0.30 and 1.0")
        if not 0.30 <= self.angular_fill <= 1.0:
            raise ValueError("angular_fill must be between 0.30 and 1.0")
        if self.center_image_png is not None and not isinstance(self.center_image_png, bytes):
            raise ValueError("center_image_png must be PNG bytes when provided")



def _point(radius: float, theta: float) -> tuple[float, float]:
    return (
        SVG_CENTER + radius * sin(theta),
        SVG_CENTER - radius * cos(theta),
    )


def _arc_path(radius: float, theta_start: float, theta_end: float) -> str:
    start_x, start_y = _point(radius, theta_start)
    end_x, end_y = _point(radius, theta_end)
    span = theta_end - theta_start
    large_arc = 1 if span > pi else 0
    return (
        f"M {start_x:.4f} {start_y:.4f} "
        f"A {radius:.4f} {radius:.4f} 0 {large_arc} 1 {end_x:.4f} {end_y:.4f}"
    )


def _cell_arc(cell: PolarCell, *, angular_fill: float) -> str:
    span = cell.theta_end - cell.theta_start
    gutter = span * (1.0 - angular_fill) / 2.0
    return _arc_path(
        cell.r_center * SVG_R,
        cell.theta_start + gutter,
        cell.theta_end - gutter,
    )


def _palette(symbol: EncodedRadialCode) -> tuple[str, ...]:
    if symbol.alphabet is Alphabet.MONO2:
        return MONO_PALETTE
    try:
        return PALETTES[symbol.palette_id]
    except KeyError as exc:
        raise ValueError(f"unknown palette id: {symbol.palette_id}") from exc


def render_svg(symbol: EncodedRadialCode, options: RenderOptions | None = None) -> str:
    options = options or RenderOptions()
    options.validate()
    palette = _palette(symbol)
    total_mm = symbol.diameter_mm * QUIET_ZONE_OUTER
    metadata = {
        "generator": "RadialCode reference renderer",
        "format_version": symbol.header.format_version,
        "geometry_version": symbol.geometry.version.number,
        "alphabet": symbol.alphabet.name,
        "palette_id": symbol.palette_id,
        "ecc_level": symbol.ecc_level.name,
        "diameter_mm": symbol.diameter_mm,
        "frame_length": len(symbol.frame.encoded_bytes),
        "center_image_embedded": options.center_image_png is not None,
        "attribution": symbol.attribution,
    }

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_mm:.4f}mm" '
            f'height="{total_mm:.4f}mm" viewBox="0 0 {SVG_CANVAS:.4f} {SVG_CANVAS:.4f}" '
            'role="img" aria-label="RadialCode symbol">'
        ),
        f"  <title>RadialCode {escape(symbol.geometry.version.name)} COLOR symbol</title>",
        f"  <desc>{escape(symbol.attribution)}</desc>",
    ]
    if options.include_attribution_metadata:
        lines.append(f"  <metadata>{escape(json.dumps(metadata, sort_keys=True, ensure_ascii=False))}</metadata>")
    lines.append(
        f'  <rect x="0" y="0" width="{SVG_CANVAS:.4f}" height="{SVG_CANVAS:.4f}" fill="{escape(options.background)}"/>'
    )

    # Continuous outer guard.
    guard_radius = ((GUARD_INNER + GUARD_OUTER) / 2.0) * SVG_R
    guard_width = (GUARD_OUTER - GUARD_INNER) * SVG_R
    lines.append(
        f'  <circle cx="{SVG_CENTER:.4f}" cy="{SVG_CENTER:.4f}" r="{guard_radius:.4f}" '
        f'fill="none" stroke="{BOOTSTRAP_DARK}" stroke-width="{guard_width:.4f}"/>'
    )

    # 64-slot clock track; light chips remain background. The Draft 0.3 band
    # is deliberately thicker than the original 128-slot experimental clock.
    clock_radius = ((CLOCK_INNER + CLOCK_OUTER) / 2.0) * SVG_R
    clock_width = (CLOCK_OUTER - CLOCK_INNER) * SVG_R * 0.90
    lines.append(f'  <g id="radialcode-clock" data-slots="{CLOCK_SLOTS}">')
    for slot, bit in enumerate(clock_track_bits()):
        if not bit:
            continue
        cell_span = TAU / CLOCK_SLOTS
        gutter = cell_span * 0.12
        start = slot * cell_span + gutter
        end = (slot + 1) * cell_span - gutter
        lines.append(
            f'    <path d="{_arc_path(clock_radius, start, end)}" fill="none" '
            f'stroke="{BOOTSTRAP_DARK}" stroke-width="{clock_width:.4f}" stroke-linecap="butt"/>'
        )
    lines.append("  </g>")

    # Draft 0.6 adds a fourth, spatially separated BCH copy beside the guard.
    header_rings = HEADER_RINGS + ((OUTER_HEADER_RING,) if symbol.header.format_version >= 5 else ())
    for copy_index, (r_inner, r_outer) in enumerate(header_rings):
        radius = ((r_inner + r_outer) / 2.0) * SVG_R
        width = (r_outer - r_inner) * SVG_R * 0.78
        for slot, bit in enumerate(header_physical_bits(symbol.header, copy_index)):
            if not bit:
                continue
            span = TAU / HEADER_PHYSICAL_SLOTS
            gutter = span * 0.13
            start = slot * span + gutter
            end = (slot + 1) * span - gutter
            lines.append(
                f'  <path d="{_arc_path(radius, start, end)}" fill="none" '
                f'stroke="{BOOTSTRAP_DARK}" stroke-width="{width:.4f}" stroke-linecap="butt"/>'
            )

    # Four asymmetric pose anchors are light notches cut through the middle of
    # the guard. The guard keeps continuous inner/outer rails for ellipse fitting,
    # while the notch widths provide rotation and identity at the same contour.
    anchor_orbit = ((ANCHOR_INNER + ANCHOR_OUTER) / 2.0) * SVG_R
    anchor_width = (ANCHOR_OUTER - ANCHOR_INNER) * SVG_R * 0.64
    for anchor in anchor_patterns():
        center = anchor.center_slot * TAU / 128.0
        half_span = anchor.width_slots * TAU / 128.0 * 0.38
        lines.append(
            f'  <path d="{_arc_path(anchor_orbit, center - half_span, center + half_span)}" '
            f'fill="none" stroke="{escape(options.background)}" stroke-width="{anchor_width:.4f}" '
            'stroke-linecap="round"/>'
        )

    # Colored payload, calibration and reserved cells.
    payload_linecap = "butt" if symbol.header.format_version >= 3 else "round"
    lines.append(
        f'  <g id="radialcode-data-cells" fill="none" stroke-linecap="{payload_linecap}">'
    )
    for cell in symbol.geometry.cells:
        state = symbol.cell_states[cell.address]
        color = palette[state]
        width = (cell.r_outer - cell.r_inner) * SVG_R * options.radial_fill
        lines.append(
            f'    <path d="{_cell_arc(cell, angular_fill=options.angular_fill)}" '
            f'stroke="{color}" stroke-width="{width:.4f}"/>'
        )
    lines.append("  </g>")

    # Center remains independent from decoding.
    logo_radius = LOGO_RADIUS * SVG_R * 0.92
    lines.append(
        f'  <circle cx="{SVG_CENTER:.4f}" cy="{SVG_CENTER:.4f}" r="{logo_radius:.4f}" '
        f'fill="{escape(options.background)}"/>'
    )
    if options.center_image_png:
        encoded_image = base64.b64encode(options.center_image_png).decode("ascii")
        clip_id = "radialcode-center-image-clip"
        lines.extend(
            [
                f'  <defs><clipPath id="{clip_id}"><circle cx="{SVG_CENTER:.4f}" cy="{SVG_CENTER:.4f}" r="{logo_radius:.4f}"/></clipPath></defs>',
                f'  <image x="{SVG_CENTER - logo_radius:.4f}" y="{SVG_CENTER - logo_radius:.4f}" width="{2 * logo_radius:.4f}" height="{2 * logo_radius:.4f}" preserveAspectRatio="none" clip-path="url(#{clip_id})" href="data:image/png;base64,{encoded_image}"/>',
            ]
        )
    if options.center_text and not options.center_image_png:
        safe_text = escape(options.center_text[:8])
        lines.append(
            f'  <text x="{SVG_CENTER:.4f}" y="{SVG_CENTER + SVG_R * 0.035:.4f}" '
            f'text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="{SVG_R * 0.12:.4f}" '
            f'font-weight="700" fill="{BOOTSTRAP_DARK}">{safe_text}</text>'
        )
    lines.append(
        f'  <circle cx="{SVG_CENTER:.4f}" cy="{SVG_CENTER:.4f}" r="{logo_radius:.4f}" '
        f'fill="none" stroke="{BOOTSTRAP_DARK}" stroke-width="{SVG_R * 0.008:.4f}"/>'
    )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def save_svg(symbol: EncodedRadialCode, path: str | Path, options: RenderOptions | None = None) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(symbol, options), encoding="utf-8")
    return output


def render_png(
    symbol: EncodedRadialCode,
    *,
    dpi: int = DEFAULT_DPI,
    options: RenderOptions | None = None,
) -> bytes:
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    total_mm = symbol.diameter_mm * QUIET_ZONE_OUTER
    pixels = max(1, int(ceil(total_mm / 25.4 * dpi)))
    svg = render_svg(symbol, options)
    return cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=pixels,
        output_height=pixels,
    )


def _raster_arc_points(
    center: float,
    radius: float,
    theta_start: float,
    theta_end: float,
    max_segment_px: float = 3.0,
) -> list[tuple[float, float]]:
    arc_length = max(1.0, abs(theta_end - theta_start) * radius)
    segments = max(2, int(ceil(arc_length / max_segment_px)))
    return [
        (
            center + radius * sin(theta_start + (theta_end - theta_start) * index / segments),
            center - radius * cos(theta_start + (theta_end - theta_start) * index / segments),
        )
        for index in range(segments + 1)
    ]


def _raster_arc(
    draw: ImageDraw.ImageDraw,
    *,
    center: float,
    radius: float,
    theta_start: float,
    theta_end: float,
    color: str,
    width: int,
    rounded: bool,
) -> None:
    points = _raster_arc_points(center, radius, theta_start, theta_end)
    draw.line(points, fill=color, width=width, joint="curve")
    if rounded:
        cap_radius = width / 2.0
        for x, y in (points[0], points[-1]):
            draw.ellipse((x - cap_radius, y - cap_radius, x + cap_radius, y + cap_radius), fill=color)


def _draw_raster_guard(
    draw: ImageDraw.ImageDraw,
    *,
    center: float,
    functional_radius: float,
    background: str,
) -> None:
    """Draw the continuous guard and its four intentional pose notches."""

    guard_radius = ((GUARD_INNER + GUARD_OUTER) / 2.0) * functional_radius
    guard_width = max(1, int(round((GUARD_OUTER - GUARD_INNER) * functional_radius)))
    draw.ellipse(
        (center - guard_radius, center - guard_radius, center + guard_radius, center + guard_radius),
        outline=BOOTSTRAP_DARK,
        width=guard_width,
    )
    anchor_orbit = ((ANCHOR_INNER + ANCHOR_OUTER) / 2.0) * functional_radius
    anchor_width = max(1, int(round((ANCHOR_OUTER - ANCHOR_INNER) * functional_radius * 0.64)))
    for anchor in anchor_patterns():
        anchor_center = anchor.center_slot * TAU / 128.0
        half_span = anchor.width_slots * TAU / 128.0 * 0.38
        _raster_arc(
            draw,
            center=center,
            radius=anchor_orbit,
            theta_start=anchor_center - half_span,
            theta_end=anchor_center + half_span,
            color=background,
            width=anchor_width,
            rounded=True,
        )


@lru_cache(maxsize=48)
def _raster_cell_paths(
    geometry_version: int,
    format_version: int,
    pixels: int,
    angular_fill: float,
    radial_fill: float,
) -> tuple[tuple[tuple[tuple[float, float], ...], int], ...]:
    geometry = geometry_for_format(geometry_version, format_version)
    functional_radius = SVG_R * (pixels / SVG_CANVAS)
    paths: list[tuple[tuple[tuple[float, float], ...], int]] = []
    for cell in geometry.cells:
        span = cell.theta_end - cell.theta_start
        gutter = span * (1.0 - angular_fill) / 2.0
        width = max(1, int(round((cell.r_outer - cell.r_inner) * functional_radius * radial_fill)))
        points = tuple(
            _raster_arc_points(
                SVG_CENTER * (pixels / SVG_CANVAS),
                cell.r_center * functional_radius,
                cell.theta_start + gutter,
                cell.theta_end - gutter,
            )
        )
        paths.append((points, width))
    return tuple(paths)


@lru_cache(maxsize=24)
def _raster_micro_cell_polygons(
    geometry_version: int,
    format_version: int,
    pixels: int,
    angular_fill: float,
    radial_fill: float,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Return filled annular sectors for very thick 2/4-ring cells."""

    geometry = geometry_for_format(geometry_version, format_version)
    functional_radius = SVG_R * (pixels / SVG_CANVAS)
    center = SVG_CENTER * (pixels / SVG_CANVAS)
    polygons: list[tuple[tuple[float, float], ...]] = []
    for cell in geometry.cells:
        span = cell.theta_end - cell.theta_start
        gutter = span * (1.0 - angular_fill) / 2.0
        start = cell.theta_start + gutter
        end = cell.theta_end - gutter
        half_width = (cell.r_outer - cell.r_inner) * radial_fill / 2.0
        inner_radius = (cell.r_center - half_width) * functional_radius
        outer_radius = (cell.r_center + half_width) * functional_radius
        outer = _raster_arc_points(center, outer_radius, start, end, max_segment_px=0.75)
        inner = list(reversed(_raster_arc_points(center, inner_radius, start, end, max_segment_px=0.75)))
        polygons.append(tuple(outer + inner))
    return tuple(polygons)


def _paste_center_image(
    image: Image.Image,
    *,
    center: float,
    logo_radius: float,
    png_bytes: bytes,
) -> None:
    """Paste a normalized square PNG into the non-functional center circle."""

    try:
        source = Image.open(BytesIO(png_bytes)).convert("RGBA")
    except OSError as exc:
        raise ValueError("center_image_png is not a readable image") from exc
    diameter = max(1, int(round(logo_radius * 2.0)))
    source = source.resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    alpha = ImageChops.multiply(source.getchannel("A"), mask)
    origin = (int(round(center - logo_radius)), int(round(center - logo_radius)))
    image.paste(source.convert("RGB"), origin, alpha)


def render_png_fast(
    symbol: EncodedRadialCode,
    *,
    dpi: int = DEFAULT_DPI,
    options: RenderOptions | None = None,
    supersample: int | None = None,
) -> bytes:
    """Render a decode-equivalent PNG directly with Pillow.

    The normative SVG renderer remains unchanged. This raster path avoids
    parsing thousands of SVG paths and is intended for interactive previews
    and digital benchmarks. It is not byte-identical to CairoSVG output.
    """

    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if supersample is None:
        supersample = (
            3
            if symbol.geometry.version.data_rings <= 4
            else 2 if symbol.geometry.version.number >= 3 else 1
        )
    if supersample not in (1, 2, 3, 4):
        raise ValueError("supersample must be between 1 and 4")
    options = options or RenderOptions()
    options.validate()
    palette = _palette(symbol)
    total_mm = symbol.diameter_mm * QUIET_ZONE_OUTER
    output_pixels = max(1, int(ceil(total_mm / 25.4 * dpi)))
    pixels = output_pixels * supersample
    scale = pixels / SVG_CANVAS
    center = SVG_CENTER * scale
    functional_radius = SVG_R * scale
    image = Image.new("RGB", (pixels, pixels), options.background)
    draw = ImageDraw.Draw(image)

    if supersample == 1:
        # The interactive Small/Micro raster intentionally avoids full-scene
        # supersampling. Render only the guard at 2× so its circumference is
        # smooth without multiplying the cost of thousands of data cells.
        guard_scale = 2
        guard_layer = Image.new("RGBA", (pixels * guard_scale, pixels * guard_scale), (0, 0, 0, 0))
        _draw_raster_guard(
            ImageDraw.Draw(guard_layer),
            center=center * guard_scale,
            functional_radius=functional_radius * guard_scale,
            background=options.background,
        )
        guard_layer = guard_layer.resize((pixels, pixels), Image.Resampling.LANCZOS)
        image = Image.alpha_composite(image.convert("RGBA"), guard_layer).convert("RGB")
        draw = ImageDraw.Draw(image)
    else:
        _draw_raster_guard(
            draw,
            center=center,
            functional_radius=functional_radius,
            background=options.background,
        )

    clock_radius = ((CLOCK_INNER + CLOCK_OUTER) / 2.0) * functional_radius
    clock_width = max(1, int(round((CLOCK_OUTER - CLOCK_INNER) * functional_radius * 0.90)))
    clock_span = TAU / CLOCK_SLOTS
    for slot, bit in enumerate(clock_track_bits()):
        if not bit:
            continue
        gutter = clock_span * 0.12
        _raster_arc(
            draw,
            center=center,
            radius=clock_radius,
            theta_start=slot * clock_span + gutter,
            theta_end=(slot + 1) * clock_span - gutter,
            color=BOOTSTRAP_DARK,
            width=clock_width,
            rounded=False,
        )

    header_rings = HEADER_RINGS + ((OUTER_HEADER_RING,) if symbol.header.format_version >= 5 else ())
    for copy_index, (r_inner, r_outer) in enumerate(header_rings):
        radius = ((r_inner + r_outer) / 2.0) * functional_radius
        width = max(1, int(round((r_outer - r_inner) * functional_radius * 0.78)))
        span = TAU / HEADER_PHYSICAL_SLOTS
        for slot, bit in enumerate(header_physical_bits(symbol.header, copy_index)):
            if not bit:
                continue
            gutter = span * 0.13
            _raster_arc(
                draw,
                center=center,
                radius=radius,
                theta_start=slot * span + gutter,
                theta_end=(slot + 1) * span - gutter,
                color=BOOTSTRAP_DARK,
                width=width,
                rounded=False,
            )

    if symbol.header.format_version >= 4 and symbol.geometry.version.data_rings <= 4:
        polygons = _raster_micro_cell_polygons(
            symbol.geometry.version.number,
            symbol.header.format_version,
            pixels,
            options.angular_fill,
            options.radial_fill,
        )
        for cell, polygon in zip(symbol.geometry.cells, polygons, strict=True):
            draw.polygon(polygon, fill=palette[symbol.cell_states[cell.address]])
    else:
        cell_paths = _raster_cell_paths(
            symbol.geometry.version.number,
            symbol.header.format_version,
            pixels,
            options.angular_fill,
            options.radial_fill,
        )
        for cell, (points, width) in zip(symbol.geometry.cells, cell_paths, strict=True):
            state = symbol.cell_states[cell.address]
            draw.line(points, fill=palette[state], width=width, joint="curve")
            if symbol.header.format_version < 3:
                cap_radius = width / 2.0
                for x, y in (points[0], points[-1]):
                    draw.ellipse((x - cap_radius, y - cap_radius, x + cap_radius, y + cap_radius), fill=palette[state])

    logo_radius = LOGO_RADIUS * functional_radius * 0.92
    logo_width = max(1, int(round(functional_radius * 0.008)))
    draw.ellipse(
        (center - logo_radius, center - logo_radius, center + logo_radius, center + logo_radius),
        fill=options.background,
    )
    if options.center_image_png:
        _paste_center_image(
            image,
            center=center,
            logo_radius=logo_radius,
            png_bytes=options.center_image_png,
        )
        draw = ImageDraw.Draw(image)
    if options.center_text and not options.center_image_png:
        text = options.center_text[:8]
        font_size = max(8, int(round(functional_radius * 0.12)))
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        bounds = draw.textbbox((0, 0), text, font=font)
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        draw.text(
            (center - text_width / 2.0, center - text_height / 2.0 - bounds[1]),
            text,
            fill=BOOTSTRAP_DARK,
            font=font,
        )
    draw.ellipse(
        (center - logo_radius, center - logo_radius, center + logo_radius, center + logo_radius),
        outline=BOOTSTRAP_DARK,
        width=logo_width,
    )

    if supersample > 1:
        image = image.resize((output_pixels, output_pixels), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG", compress_level=3)
    return output.getvalue()


def save_png(
    symbol: EncodedRadialCode,
    path: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    options: RenderOptions | None = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(render_png(symbol, dpi=dpi, options=options))
    return output
