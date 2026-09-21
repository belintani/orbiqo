#!/usr/bin/env python3
"""Run a real-camera corpus through native C++ and the Python oracle.

The corpus is intentionally external to Git: images may contain private scenes
or metadata. The report stores image hashes and decode hashes, not image bytes
or decoded payloads.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "server/python/native/orbiqo_native"
BRIDGE = ROOT / "server/python/orbiqo_bridge.py"
REFERENCE_ROOT = ROOT / "server/python/vendor/radialcode"


@dataclass(frozen=True)
class DecodeObservation:
    ok: bool
    payload_sha256: str | None
    payload_bytes: int | None
    message: str
    elapsed_ms: float


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_native_result(stdout: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line in {"ORBIQO_NATIVE_RESULT_V1", "END"}:
            continue
        if " " not in line:
            continue
        key, value = line.split(" ", 1)
        fields[key] = value
    return fields


def native_decode(image: bytes, timeout_seconds: int) -> DecodeObservation:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [str(NATIVE)],
            input=(
                "OP decode\n"
                f"IMAGE_HEX {image.hex()}\n"
                "CANONICAL 0\n"
                "ERASURE_THRESHOLD 0.55\n"
                "END\n"
            ).encode("ascii"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except Exception as exc:  # pragma: no cover - defensive process boundary
        elapsed = (time.perf_counter() - started) * 1000.0
        return DecodeObservation(False, None, None, f"native process error: {exc}", elapsed)

    elapsed = (time.perf_counter() - started) * 1000.0
    fields = parse_native_result(completed.stdout)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        return DecodeObservation(False, None, None, detail[:240] or f"native exit {completed.returncode}", elapsed)
    payload_hex = fields.get("payload_hex")
    if not payload_hex:
        return DecodeObservation(False, None, None, "native response did not contain payload_hex", elapsed)
    try:
        payload = bytes.fromhex(payload_hex)
    except ValueError:
        return DecodeObservation(False, None, None, "native payload_hex is invalid", elapsed)
    return DecodeObservation(True, sha256_bytes(payload), len(payload), "ok", elapsed)


def python_oracle_decode(image: bytes, timeout_seconds: int) -> DecodeObservation:
    started = time.perf_counter()
    request = {
        "op": "decode",
        "image_base64": base64.b64encode(image).decode("ascii"),
        "canonical": False,
        "output_size": 1024,
        "erasure_threshold": 0.55,
        "decoder_backend": "reference",
    }
    try:
        completed = subprocess.run(
            [sys.executable, str(BRIDGE)],
            input=(json.dumps(request) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
            env={
                **__import__("os").environ,
                "ORBIQO_RADIALCODE_ROOT": str(REFERENCE_ROOT),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive process boundary
        elapsed = (time.perf_counter() - started) * 1000.0
        return DecodeObservation(False, None, None, f"oracle process error: {exc}", elapsed)

    elapsed = (time.perf_counter() - started) * 1000.0
    try:
        response = json.loads(completed.stdout.decode("utf-8"))
    except Exception:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        return DecodeObservation(False, None, None, f"invalid oracle output: {detail[:180]}", elapsed)
    if not response.get("ok"):
        error = response.get("error") or {}
        return DecodeObservation(False, None, None, str(error.get("message", "oracle decode failed"))[:240], elapsed)
    result = response.get("result") or {}
    payload_b64 = result.get("payload_base64")
    if not isinstance(payload_b64, str):
        return DecodeObservation(False, None, None, "oracle response did not contain payload_base64", elapsed)
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except Exception:
        return DecodeObservation(False, None, None, "oracle payload_base64 is invalid", elapsed)
    return DecodeObservation(True, sha256_bytes(payload), len(payload), "ok", elapsed)


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "width": image.width,
            "height": image.height,
            "format": image.format,
            "mode": image.mode,
        }


def expected_hash(case: dict[str, Any]) -> str | None:
    explicit = case.get("expected_payload_sha256")
    if isinstance(explicit, str) and explicit.strip():
        normalized = explicit.strip().lower()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError(f"{case.get('id', '<unknown>')}: expected_payload_sha256 must be 64 hex characters")
        return normalized
    payload_hex = case.get("expected_payload_hex")
    if isinstance(payload_hex, str) and payload_hex.strip():
        try:
            return sha256_bytes(bytes.fromhex(payload_hex.strip()))
        except ValueError as exc:
            raise ValueError(f"{case.get('id', '<unknown>')}: expected_payload_hex is invalid") from exc
    return None


def observation_json(observation: DecodeObservation, expected: str | None) -> dict[str, Any]:
    return {
        "ok": observation.ok,
        "payload_sha256": observation.payload_sha256,
        "payload_bytes": observation.payload_bytes,
        "exact_match": expected is not None and observation.payload_sha256 == expected,
        "verified": expected is not None,
        "message": observation.message,
        "elapsed_ms": round(observation.elapsed_ms, 3),
    }


def run_case(corpus_root: Path, case: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    case_id = str(case.get("id", "")).strip()
    if not case_id:
        raise ValueError("every case requires a non-empty id")
    image_value = case.get("image")
    if not isinstance(image_value, str) or not image_value.strip():
        raise ValueError(f"{case_id}: every case requires an image path")
    image_path = (corpus_root / image_value).resolve()
    if corpus_root.resolve() not in image_path.parents:
        raise ValueError(f"{case_id}: image path escapes corpus root")
    if not image_path.is_file():
        raise FileNotFoundError(f"{case_id}: image not found: {image_value}")
    image = image_path.read_bytes()
    expected = expected_hash(case)
    native = native_decode(image, timeout_seconds)
    oracle = python_oracle_decode(image, timeout_seconds)
    return {
        "id": case_id,
        "image": {
            "path": image_value,
            "sha256": sha256_bytes(image),
            "bytes": len(image),
            **image_metadata(image_path),
        },
        "capture": case.get("capture", {}),
        "geometry": case.get("geometry"),
        "expected_payload_sha256": expected,
        "native_cpp": observation_json(native, expected),
        "python_oracle": observation_json(oracle, expected),
        "agreement": {
            "both_ok": native.ok and oracle.ok,
            "payload_hashes_equal": native.payload_sha256 is not None and native.payload_sha256 == oracle.payload_sha256,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="local corpus root containing the manifest image paths")
    parser.add_argument("--manifest", type=Path, required=True, help="JSON manifest, relative to --root unless absolute")
    parser.add_argument("--output", type=Path, required=True, help="JSON report destination")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--require-exact", action="store_true", help="fail if any case lacks an expected hash or exact match")
    args = parser.parse_args()

    corpus_root = args.root.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else corpus_root / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise SystemExit("unsupported manifest schema_version; expected 1")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SystemExit("manifest must contain a non-empty cases array")

    rows = [run_case(corpus_root, case, args.timeout_seconds) for case in cases]
    all_verified = all(row["native_cpp"]["verified"] and row["python_oracle"]["verified"] for row in rows)
    native_exact = sum(bool(row["native_cpp"]["exact_match"]) for row in rows)
    oracle_exact = sum(bool(row["python_oracle"]["exact_match"]) for row in rows)
    output = {
        "schema_version": 1,
        "scope": "real-camera corpus supplied externally; images are not copied into the report; native C++ is production path and Python is oracle only",
        "manifest": str(manifest_path.relative_to(corpus_root)),
        "corpus_label": manifest.get("corpus_label"),
        "capture_protocol_version": manifest.get("capture_protocol_version"),
        "total_cases": len(rows),
        "native_exact_cases": native_exact,
        "oracle_exact_cases": oracle_exact,
        "both_exact_cases": sum(bool(row["native_cpp"]["exact_match"] and row["python_oracle"]["exact_match"]) for row in rows),
        "all_cases_verified": all_verified,
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "cases"}, indent=2, ensure_ascii=False))

    if args.require_exact and (not all_verified or native_exact != len(rows) or oracle_exact != len(rows)):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
