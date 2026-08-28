"""Command-line interfaces for the RadialCode reference package."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys

from .capacity import capacity_for
from .constants import GEOMETRY_VERSIONS, Alphabet, EccLevel, PayloadType
from .decoder import decode_canonical
from .encoder import encode
from .renderer import RenderOptions, save_png, save_svg


_ECC_NAMES = {
    "fast": EccLevel.FAST,
    "balanced": EccLevel.BALANCED,
    "robust": EccLevel.ROBUST,
    "extreme": EccLevel.EXTREME,
}
_ALPHABET_NAMES = {"color4": Alphabet.COLOR4, "mono2": Alphabet.MONO2}
_PAYLOAD_NAMES = {"binary": PayloadType.BINARY, "text": PayloadType.UTF8, "url": PayloadType.URL}


def _geometry_value(raw: str) -> int | str:
    if raw == "auto":
        return raw
    if raw in ("small", "medium", "large", "xl"):
        return raw
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("geometry must be auto, small, medium, large, xl or 1–4") from exc
    if value not in GEOMETRY_VERSIONS:
        raise argparse.ArgumentTypeError("geometry version must be 1–4")
    return value


def _source_payload(args: argparse.Namespace) -> tuple[bytes | str, PayloadType | None]:
    if args.text is not None:
        payload_type = _PAYLOAD_NAMES.get(args.payload_type) if args.payload_type != "auto" else None
        return args.text, payload_type
    if args.input is not None:
        payload = Path(args.input).read_bytes()
        payload_type = _PAYLOAD_NAMES.get(args.payload_type) if args.payload_type != "auto" else PayloadType.BINARY
        return payload, payload_type
    if not sys.stdin.isatty():
        data = sys.stdin.buffer.read()
        payload_type = _PAYLOAD_NAMES.get(args.payload_type) if args.payload_type != "auto" else PayloadType.BINARY
        return data, payload_type
    raise SystemExit("provide --text, --input or data on stdin")


def generate_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate a COLOR4 RadialCode SVG/PNG")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="text or URL payload")
    source.add_argument("--input", help="binary payload file")
    parser.add_argument("--payload-type", choices=("auto", "binary", "text", "url"), default="auto")
    parser.add_argument("--geometry", type=_geometry_value, default="auto")
    parser.add_argument("--diameter-mm", type=float)
    parser.add_argument("--alphabet", choices=tuple(_ALPHABET_NAMES), default="color4")
    parser.add_argument("--ecc", choices=tuple(_ECC_NAMES), default="balanced")
    parser.add_argument("--compression", choices=("auto", "none", "deflate"), default="auto")
    parser.add_argument("--output", required=True, help="output file or stem")
    parser.add_argument("--format", choices=("svg", "png", "both"), default="both")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--center-text", default=None, help="optional non-functional center text, up to 8 chars")
    args = parser.parse_args(argv)

    payload, payload_type = _source_payload(args)
    symbol = encode(
        payload,
        payload_type=payload_type,
        geometry=args.geometry,
        diameter_mm=args.diameter_mm,
        alphabet=_ALPHABET_NAMES[args.alphabet],
        ecc_level=_ECC_NAMES[args.ecc],
        compression=args.compression,
    )
    options = RenderOptions(center_text=args.center_text)
    output = Path(args.output)
    if args.format == "svg":
        path = output if output.suffix.lower() == ".svg" else output.with_suffix(".svg")
        save_svg(symbol, path, options)
        files = [path]
    elif args.format == "png":
        path = output if output.suffix.lower() == ".png" else output.with_suffix(".png")
        save_png(symbol, path, dpi=args.dpi, options=options)
        files = [path]
    else:
        stem = output.with_suffix("") if output.suffix else output
        svg = save_svg(symbol, stem.with_suffix(".svg"), options)
        png = save_png(symbol, stem.with_suffix(".png"), dpi=args.dpi, options=options)
        files = [svg, png]

    summary = {
        "files": [str(path) for path in files],
        "geometry_version": symbol.geometry.version.number,
        "geometry_name": symbol.geometry.version.name,
        "diameter_mm": symbol.diameter_mm,
        "physical_pitch_mm": symbol.diagnostics.physical_pitch_mm,
        "print_pitch_warning": symbol.diagnostics.print_pitch_warning,
        "alphabet": symbol.alphabet.name,
        "ecc_level": symbol.ecc_level.name,
        "payload_bytes": len(symbol.payload),
        "frame_bytes": len(symbol.frame.encoded_bytes),
        "mask_id": symbol.header.mask_id,
        "attribution": symbol.attribution,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _decoded_json(result, rectification=None) -> dict[str, object]:
    diagnostics = result.diagnostics
    output: dict[str, object] = {
        "payload_base64": base64.b64encode(result.payload).decode("ascii"),
        "payload_type": result.frame.payload_type.name,
        "payload_bytes": len(result.payload),
        "geometry_version": result.header.geometry_version,
        "alphabet": result.header.alphabet.name,
        "palette_id": result.header.palette_id,
        "ecc_level": result.header.ecc_level.name,
        "mask_id": result.header.mask_id,
        "header_corrected_bits": list(diagnostics.header_corrected_bits),
        "corrected_rs_symbols": diagnostics.corrected_rs_symbols,
        "erasure_cells": diagnostics.erasure_cells,
        "erasure_bytes": diagnostics.erasure_bytes,
        "average_confidence": diagnostics.average_confidence,
        "minimum_confidence": diagnostics.minimum_confidence,
        "processing_time_ms": diagnostics.processing_time_ms,
    }
    if result.frame.payload_type in (PayloadType.UTF8, PayloadType.URL):
        output["text"] = result.payload.decode("utf-8")
    if rectification is not None:
        output["rectification"] = {
            "axis_ratio": rectification.ellipse.axis_ratio,
            "anchor_widths": list(rectification.anchor_run_lengths),
            "reprojection_error_px": rectification.reprojection_error_px,
            "homography": [list(row) for row in rectification.homography],
        }
    return output


def decode_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Decode a RadialCode image")
    parser.add_argument("image")
    parser.add_argument("--canonical", action="store_true", help="skip detection; image is centered and front-facing")
    parser.add_argument("--geometry", type=int, choices=tuple(GEOMETRY_VERSIONS))
    parser.add_argument("--output", help="write raw payload bytes")
    parser.add_argument("--json", action="store_true", help="emit structured diagnostics")
    parser.add_argument("--output-size", type=int, default=1024)
    parser.add_argument("--erasure-threshold", type=float, default=0.55)
    args = parser.parse_args(argv)

    if args.canonical:
        decoded = decode_canonical(
            args.image,
            geometry_hint=args.geometry,
            erasure_threshold=args.erasure_threshold,
        )
        rectification = None
    else:
        try:
            from .vision import decode_image
        except ImportError as exc:
            raise SystemExit("camera-image decoding requires: pip install 'radialcode[vision]'") from exc
        detected = decode_image(
            args.image,
            output_size=args.output_size,
            erasure_threshold=args.erasure_threshold,
        )
        decoded = detected.decoded
        rectification = detected.rectification

    if args.output:
        Path(args.output).write_bytes(decoded.payload)
    if args.json:
        print(json.dumps(_decoded_json(decoded, rectification), indent=2, ensure_ascii=False))
    elif not args.output:
        if decoded.frame.payload_type in (PayloadType.UTF8, PayloadType.URL):
            print(decoded.payload.decode("utf-8"))
        else:
            print(base64.b64encode(decoded.payload).decode("ascii"))


def inspect_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Inspect nominal RadialCode capacities")
    parser.add_argument("--alphabet", choices=tuple(_ALPHABET_NAMES), default="color4")
    parser.add_argument("--ecc", choices=tuple(_ECC_NAMES), default="balanced")
    args = parser.parse_args(argv)
    alphabet = _ALPHABET_NAMES[args.alphabet]
    ecc_level = _ECC_NAMES[args.ecc]

    print("version,name,rings,recommended_diameter_mm,payload_cells,channel_bytes,max_payload_bytes")
    for version in sorted(GEOMETRY_VERSIONS):
        geometry = GEOMETRY_VERSIONS[version]
        capacity = capacity_for(version, alphabet, ecc_level)
        print(
            f"{version},{geometry.name},{geometry.data_rings},{geometry.recommended_diameter_mm:.1f},"
            f"{capacity.payload_cells},{capacity.channel_bytes},{capacity.maximum_uncompressed_payload_bytes}"
        )


if __name__ == "__main__":  # pragma: no cover
    generate_main()
