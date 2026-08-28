"""OpenCV detection and homography rectification for RadialCode images."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import cos, pi, sin
from pathlib import Path
from typing import Iterator, Sequence

import cv2
import numpy as np
from PIL import Image

from .bootstrap import anchor_patterns
from .constants import ANCHOR_INNER, ANCHOR_OUTER, GUARD_OUTER, QUIET_ZONE_OUTER
from .decoder import DecodeError, DecodedRadialCode, decode_canonical

TAU = 2.0 * pi


class DetectionError(ValueError):
    """Raised when a symbol candidate or its anchors cannot be recovered."""


@dataclass(frozen=True, slots=True)
class EllipseCandidate:
    center: tuple[float, float]
    axes: tuple[float, float]
    angle_degrees: float
    contour_area: float
    axis_ratio: float
    circularity: float
    score: float


@dataclass(frozen=True, slots=True)
class RectificationDiagnostics:
    ellipse: EllipseCandidate
    anchor_run_lengths: tuple[int, ...]
    anchor_source_points: tuple[tuple[float, float], ...]
    anchor_target_points: tuple[tuple[float, float], ...]
    homography: tuple[tuple[float, float, float], ...]
    reprojection_error_px: float
    output_size: int


@dataclass(frozen=True, slots=True)
class RectificationResult:
    image: Image.Image
    diagnostics: RectificationDiagnostics


@dataclass(frozen=True, slots=True)
class DetectedDecode:
    decoded: DecodedRadialCode
    rectification: RectificationDiagnostics



def _load_bgr(image: str | Path | bytes | Image.Image) -> np.ndarray:
    if isinstance(image, (str, Path)):
        loaded = Image.open(image)
    elif isinstance(image, bytes):
        loaded = Image.open(BytesIO(image))
    elif isinstance(image, Image.Image):
        loaded = image
    else:
        raise TypeError("image must be a path, PNG bytes or PIL Image")
    loaded = loaded.convert("RGB")
    rgb = np.asarray(loaded, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _ellipse_candidate(contour: np.ndarray) -> EllipseCandidate | None:
    if len(contour) < 5:
        return None
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    if area <= 0 or perimeter <= 0:
        return None
    (center_x, center_y), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
    major = max(float(axis_a), float(axis_b))
    minor = min(float(axis_a), float(axis_b))
    if major <= 0:
        return None
    ratio = minor / major
    circularity = min(1.0, 4.0 * pi * area / (perimeter * perimeter))
    fitted_ellipse_area = pi * major * minor / 4.0
    score = fitted_ellipse_area * (0.50 + ratio)
    return EllipseCandidate(
        center=(float(center_x), float(center_y)),
        axes=(float(axis_a), float(axis_b)),
        angle_degrees=float(angle),
        contour_area=area,
        axis_ratio=ratio,
        circularity=circularity,
        score=score,
    )


def _detect_outer_guard_bgr(bgr: np.ndarray) -> EllipseCandidate:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    image_area = float(gray.shape[0] * gray.shape[1])
    candidates: list[EllipseCandidate] = []
    for contour in contours:
        candidate = _ellipse_candidate(contour)
        if candidate is None:
            continue
        fitted_area = pi * candidate.axes[0] * candidate.axes[1] / 4.0
        fitted_area_fraction = fitted_area / image_area
        if not 0.04 <= fitted_area_fraction <= 1.10:
            continue
        center_x, center_y = candidate.center
        if not (0 <= center_x < gray.shape[1] and 0 <= center_y < gray.shape[0]):
            continue
        if candidate.axis_ratio < 0.22:
            continue
        candidates.append(candidate)

    if not candidates:
        raise DetectionError("no plausible outer guard ellipse was found")
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[0]


def _dark_extent_guard_candidate(bgr: np.ndarray) -> EllipseCandidate:
    """Estimate a frontal guard from the dark-symbol extent as a fallback.

    A localized white obstruction can split the guard contour and bias an ellipse
    fit. For an already near-frontal image, the extrema of the remaining dark
    guard rails retain a stable center and diameter. This is attempted only
    after canonical and primary-ellipse paths have failed.
    """

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    dark = cv2.inRange(gray, 0, 88)
    points = cv2.findNonZero(dark)
    if points is None:
        raise DetectionError("no dark extent was found for frontal fallback")
    x, y, width, height = cv2.boundingRect(points)
    image_height, image_width = gray.shape[:2]
    area_fraction = (width * height) / float(image_width * image_height)
    ratio = min(width, height) / max(width, height)
    if area_fraction < 0.04 or ratio < 0.88:
        raise DetectionError("dark extent is not a plausible frontal guard")
    center = (x + width / 2.0, y + height / 2.0)
    return EllipseCandidate(
        center=center,
        axes=(float(width), float(height)),
        angle_degrees=0.0,
        contour_area=float(width * height),
        axis_ratio=ratio,
        circularity=ratio,
        score=float(width * height),
    )


def detect_outer_guard(image: str | Path | bytes | Image.Image) -> EllipseCandidate:
    return _detect_outer_guard_bgr(_load_bgr(image))


def _frontal_rectification(
    bgr: np.ndarray,
    candidate: EllipseCandidate,
    output_size: int,
) -> RectificationResult:
    source_guard_radius = (candidate.axes[0] + candidate.axes[1]) / 4.0
    if source_guard_radius <= 0:
        raise DetectionError("outer guard has invalid frontal radius")
    target_center = output_size / 2.0
    target_functional_radius = output_size / (2.0 * QUIET_ZONE_OUTER)
    target_guard_radius = target_functional_radius * GUARD_OUTER
    scale = target_guard_radius / source_guard_radius
    center_x, center_y = candidate.center
    affine = np.float32(
        [
            [scale, 0.0, target_center - scale * center_x],
            [0.0, scale, target_center - scale * center_y],
        ]
    )
    rectified = cv2.warpAffine(
        bgr,
        affine,
        (output_size, output_size),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    homography = np.vstack((affine, np.float32((0.0, 0.0, 1.0))))
    diagnostics = RectificationDiagnostics(
        ellipse=candidate,
        anchor_run_lengths=(),
        anchor_source_points=(),
        anchor_target_points=(),
        homography=tuple(tuple(float(value) for value in row) for row in homography),
        reprojection_error_px=0.0,
        output_size=output_size,
    )
    rgb = cv2.cvtColor(rectified, cv2.COLOR_BGR2RGB)
    return RectificationResult(Image.fromarray(rgb), diagnostics)


def _ellipse_affine(candidate: EllipseCandidate, output_size: int) -> np.ndarray:
    center = np.asarray(candidate.center, dtype=np.float32)
    axis_a, axis_b = candidate.axes
    phi = candidate.angle_degrees * pi / 180.0
    vector_a = np.asarray((cos(phi) * axis_a / 2.0, sin(phi) * axis_a / 2.0), dtype=np.float32)
    vector_b = np.asarray((-sin(phi) * axis_b / 2.0, cos(phi) * axis_b / 2.0), dtype=np.float32)
    source = np.float32([center, center + vector_a, center + vector_b])

    target_center = np.float32((output_size / 2.0, output_size / 2.0))
    functional_radius = output_size / (2.0 * QUIET_ZONE_OUTER)
    guard_radius = functional_radius * GUARD_OUTER
    target = np.float32(
        [
            target_center,
            target_center + np.float32((guard_radius, 0.0)),
            target_center + np.float32((0.0, guard_radius)),
        ]
    )
    return cv2.getAffineTransform(source, target)


def _adaptive_threshold(values: Sequence[float]) -> float:
    low = min(values)
    high = max(values)
    for _ in range(16):
        midpoint = (low + high) / 2.0
        first = [value for value in values if value <= midpoint]
        second = [value for value in values if value > midpoint]
        if not first or not second:
            break
        next_low = sum(first) / len(first)
        next_high = sum(second) / len(second)
        if abs(next_low - low) + abs(next_high - high) < 0.02:
            low, high = next_low, next_high
            break
        low, high = next_low, next_high
    if high - low < 8.0:
        raise DetectionError("anchor annulus has insufficient luminance separation")
    return (low + high) / 2.0


def _circular_dark_runs(bits: Sequence[int]) -> list[tuple[int, int, float]]:
    if not bits or all(bits) or not any(bits):
        return []
    length = len(bits)
    light_index = next(index for index, value in enumerate(bits) if value == 0)
    start = (light_index + 1) % length
    ordered = [bits[(start + index) % length] for index in range(length)]
    runs: list[tuple[int, int, float]] = []
    index = 0
    while index < length:
        if ordered[index] == 0:
            index += 1
            continue
        run_start = index
        while index < length and ordered[index] == 1:
            index += 1
        run_length = index - run_start
        center_ordered = run_start + (run_length - 1) / 2.0
        center_original = (start + center_ordered) % length
        runs.append((run_start, run_length, center_original))
    return runs


def _anchor_points_from_coarse(coarse: np.ndarray, sample_count: int = 1024) -> tuple[list[np.ndarray], tuple[int, ...]]:
    gray = cv2.cvtColor(coarse, cv2.COLOR_BGR2GRAY)
    size = coarse.shape[0]
    center = size / 2.0
    functional_radius = size / (2.0 * QUIET_ZONE_OUTER)

    # The fitted contour may correspond to either rail of the thick guard. Find
    # the actual notch center by scanning radii and scoring the global 3:5:7:9
    # width signature. Data rings produce many runs; background produces none.
    best_radius: float | None = None
    best_score = float("-inf")
    expected_widths = np.asarray((3.0, 5.0, 7.0, 9.0), dtype=np.float64)
    expected_gaps = np.asarray((19.0, 27.0, 35.0, 47.0), dtype=np.float64)
    scan_count = 512
    for normalized_radius in np.linspace(0.915, 1.025, 89):
        radius = normalized_radius * functional_radius
        samples: list[float] = []
        for index in range(scan_count):
            theta = index * TAU / scan_count
            x = center + radius * sin(theta)
            y = center - radius * cos(theta)
            ix = int(round(x))
            iy = int(round(y))
            if not (0 <= ix < size and 0 <= iy < size):
                continue
            samples.append(float(gray[iy, ix]))
        if len(samples) != scan_count:
            continue
        try:
            threshold = _adaptive_threshold(samples)
        except DetectionError:
            continue
        bits = [1 if value > threshold else 0 for value in samples]
        runs = [run for run in _circular_dark_runs(bits) if 3 <= run[1] <= scan_count // 8]
        if len(runs) < 4:
            continue
        selected_runs = sorted(runs, key=lambda item: item[1], reverse=True)[:4]
        selected_runs.sort(key=lambda item: item[1])
        selected_widths = np.asarray([run[1] for run in selected_runs], dtype=np.float64)
        scale = float(np.dot(selected_widths, expected_widths) / np.dot(expected_widths, expected_widths))
        if scale <= 0:
            continue
        relative_error = float(
            np.mean(np.abs(selected_widths - scale * expected_widths) / (scale * expected_widths))
        )
        centers = np.asarray([run[2] for run in selected_runs], dtype=np.float64)
        gaps = np.asarray(
            [
                (centers[1] - centers[0]) % scan_count,
                (centers[2] - centers[1]) % scan_count,
                (centers[3] - centers[2]) % scan_count,
                (centers[0] - centers[3]) % scan_count,
            ],
            dtype=np.float64,
        )
        expected_gap_samples = expected_gaps * scan_count / 128.0
        spacing_error = float(np.mean(np.abs(gaps - expected_gap_samples) / expected_gap_samples))
        contrast = float(np.percentile(samples, 96) - np.percentile(samples, 50))
        score = (
            500.0
            - 160.0 * relative_error
            - 260.0 * spacing_error
            - 10.0 * abs(len(runs) - 4)
            + 0.10 * contrast
        )
        if score > best_score:
            best_score = score
            best_radius = float(normalized_radius)
    if best_radius is None:
        raise DetectionError("could not locate the four guard-notch anchors")

    orbit = best_radius * functional_radius
    luminances: list[float] = []
    points: list[np.ndarray] = []
    radial_samples = np.linspace(best_radius - 0.003, best_radius + 0.003, 3)
    for index in range(sample_count):
        theta = index * TAU / sample_count
        values: list[float] = []
        for normalized_radius in radial_samples:
            radius = normalized_radius * functional_radius
            x = center + radius * sin(theta)
            y = center - radius * cos(theta)
            values.append(float(gray[int(round(y)), int(round(x))]))
        # A pose marker is a light notch through the dark guard center.
        luminances.append(max(values))
        points.append(
            np.asarray(
                (center + orbit * sin(theta), center - orbit * cos(theta)),
                dtype=np.float32,
            )
        )

    threshold = _adaptive_threshold(luminances)
    bits = [1 if value > threshold else 0 for value in luminances]
    minimum = max(3, sample_count // 256)
    maximum = sample_count // 8
    runs = [run for run in _circular_dark_runs(bits) if minimum <= run[1] <= maximum]
    if len(runs) < 4:
        raise DetectionError(f"found only {len(runs)} anchor runs")

    # The four normative notch widths are strictly increasing. Select the four
    # widest plausible light runs and assign identity from shortest to longest.
    selected = sorted(runs, key=lambda item: item[1], reverse=True)[:4]
    selected.sort(key=lambda item: item[1])
    detected = [points[int(round(run[2])) % sample_count] for run in selected]
    lengths = tuple(run[1] for run in selected)
    return detected, lengths


def _anchor_points_from_guard_holes(
    bgr: np.ndarray,
    candidate: EllipseCandidate,
) -> tuple[list[np.ndarray], tuple[int, ...]]:
    """Locate the four light guard notches as connected components.

    The notches are enclosed by the continuous inner and outer guard rails. This
    makes them isolated light components in the source image even under strong
    projective distortion.
    """

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, light = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(light, connectivity=8)
    image_area = gray.shape[0] * gray.shape[1]
    axis_a, axis_b = candidate.axes
    phi = candidate.angle_degrees * pi / 180.0
    basis_a = np.asarray((cos(phi), sin(phi)), dtype=np.float64)
    basis_b = np.asarray((-sin(phi), cos(phi)), dtype=np.float64)
    center = np.asarray(candidate.center, dtype=np.float64)

    components: list[tuple[int, np.ndarray]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not 12 <= area <= max(20, int(image_area * 0.008)):
            continue
        point = np.asarray(centroids[label], dtype=np.float64)
        delta = point - center
        coordinate_a = float(np.dot(delta, basis_a) / (axis_a / 2.0))
        coordinate_b = float(np.dot(delta, basis_b) / (axis_b / 2.0))
        elliptical_radius = float(np.hypot(coordinate_a, coordinate_b))
        if not 0.84 <= elliptical_radius <= 1.16:
            continue
        components.append((area, point.astype(np.float32)))

    if len(components) < 4:
        raise DetectionError(f"found only {len(components)} isolated guard notches")

    # Select four large light islands and map identity from increasing area.
    selected = sorted(components, key=lambda item: item[0], reverse=True)[:4]
    selected.sort(key=lambda item: item[0])
    points = [point for _, point in selected]
    areas = tuple(area for area, _ in selected)
    return points, areas


def _target_anchor_points(output_size: int) -> list[np.ndarray]:
    center = output_size / 2.0
    functional_radius = output_size / (2.0 * QUIET_ZONE_OUTER)
    radius = ((ANCHOR_INNER + ANCHOR_OUTER) / 2.0) * functional_radius
    targets: list[np.ndarray] = []
    for anchor in anchor_patterns():
        theta = anchor.center_slot * TAU / 128.0
        targets.append(
            np.asarray((center + radius * sin(theta), center - radius * cos(theta)), dtype=np.float32)
        )
    return targets


def _coarse_anchor_points_in_source(
    bgr: np.ndarray,
    candidate: EllipseCandidate,
    output_size: int,
) -> tuple[list[np.ndarray], tuple[int, ...]]:
    affine = _ellipse_affine(candidate, output_size)
    coarse = cv2.warpAffine(
        bgr,
        affine,
        (output_size, output_size),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    coarse_points, run_lengths = _anchor_points_from_coarse(coarse)
    inverse_affine = cv2.invertAffineTransform(affine)
    source_points: list[np.ndarray] = []
    for point in coarse_points:
        homogeneous = np.asarray((point[0], point[1], 1.0), dtype=np.float32)
        source_points.append(inverse_affine @ homogeneous)
    return source_points, run_lengths


def _rectify_from_points(
    bgr: np.ndarray,
    candidate: EllipseCandidate,
    source_points: Sequence[np.ndarray],
    run_lengths: tuple[int, ...],
    output_size: int,
) -> RectificationResult:
    target_points = _target_anchor_points(output_size)
    source_array = np.float32(source_points)
    target_array = np.float32(target_points)
    homography = cv2.getPerspectiveTransform(source_array, target_array)
    canonical = cv2.warpPerspective(
        bgr,
        homography,
        (output_size, output_size),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )

    source_h = np.hstack((source_array, np.ones((4, 1), dtype=np.float32)))
    projected = (homography @ source_h.T).T
    projected = projected[:, :2] / projected[:, 2:3]
    reprojection_error = float(np.mean(np.linalg.norm(projected - target_array, axis=1)))
    rgb = cv2.cvtColor(canonical, cv2.COLOR_BGR2RGB)
    diagnostics = RectificationDiagnostics(
        ellipse=candidate,
        anchor_run_lengths=run_lengths,
        anchor_source_points=tuple((float(point[0]), float(point[1])) for point in source_points),
        anchor_target_points=tuple((float(point[0]), float(point[1])) for point in target_points),
        homography=tuple(tuple(float(value) for value in row) for row in homography),
        reprojection_error_px=reprojection_error,
        output_size=output_size,
    )
    return RectificationResult(image=Image.fromarray(rgb, mode="RGB"), diagnostics=diagnostics)


def _rectify_affine_from_points(
    bgr: np.ndarray,
    candidate: EllipseCandidate,
    source_points: Sequence[np.ndarray],
    run_lengths: tuple[int, ...],
    output_size: int,
) -> RectificationResult:
    target_points = _target_anchor_points(output_size)
    source_array = np.float32(source_points)
    target_array = np.float32(target_points)
    affine, _ = cv2.estimateAffine2D(source_array, target_array, method=cv2.LMEDS)
    if affine is None:
        raise DetectionError("affine anchor fit failed")
    canonical = cv2.warpAffine(
        bgr,
        affine,
        (output_size, output_size),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    projected = cv2.transform(source_array[None, :, :], affine)[0]
    reprojection_error = float(np.mean(np.linalg.norm(projected - target_array, axis=1)))
    homography = np.vstack((affine, np.asarray((0.0, 0.0, 1.0), dtype=np.float64)))
    rgb = cv2.cvtColor(canonical, cv2.COLOR_BGR2RGB)
    diagnostics = RectificationDiagnostics(
        ellipse=candidate,
        anchor_run_lengths=run_lengths,
        anchor_source_points=tuple((float(point[0]), float(point[1])) for point in source_points),
        anchor_target_points=tuple((float(point[0]), float(point[1])) for point in target_points),
        homography=tuple(tuple(float(value) for value in row) for row in homography),
        reprojection_error_px=reprojection_error,
        output_size=output_size,
    )
    return RectificationResult(image=Image.fromarray(rgb, mode="RGB"), diagnostics=diagnostics)


def _rectification_candidates(
    image: str | Path | bytes | Image.Image,
    *,
    output_size: int,
) -> Iterator[RectificationResult]:
    if output_size < 256:
        raise ValueError("output_size must be at least 256 pixels")
    bgr = _load_bgr(image)
    candidate = detect_outer_guard(image)
    signatures: set[tuple[tuple[int, int], ...]] = set()
    yielded = 0
    strategy_loaders = (
        lambda: _anchor_points_from_guard_holes(bgr, candidate),
        lambda: _coarse_anchor_points_in_source(bgr, candidate, output_size),
    )
    for load_strategy in strategy_loaders:
        try:
            source_points, run_lengths = load_strategy()
        except DetectionError:
            continue
        signature = tuple((int(round(point[0])), int(round(point[1]))) for point in source_points)
        if signature in signatures:
            continue
        signatures.add(signature)
        yielded += 1
        yield _rectify_from_points(bgr, candidate, source_points, run_lengths, output_size)
        try:
            affine = _rectify_affine_from_points(bgr, candidate, source_points, run_lengths, output_size)
        except DetectionError:
            continue
        yielded += 1
        yield affine
    if yielded == 0:
        raise DetectionError("could not recover a usable set of guard-notch anchors")


def rectify(
    image: str | Path | bytes | Image.Image,
    *,
    output_size: int = 1024,
) -> RectificationResult:
    return next(_rectification_candidates(image, output_size=output_size))


def decode_image(
    image: str | Path | bytes | Image.Image,
    *,
    output_size: int = 1024,
    erasure_threshold: float = 0.55,
) -> DetectedDecode:
    last_error: DecodeError | None = None
    bgr = _load_bgr(image)
    try:
        guard = _detect_outer_guard_bgr(bgr)
        if guard.axis_ratio >= 0.96:
            direct_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            try:
                decoded = decode_canonical(Image.fromarray(direct_rgb), erasure_threshold=erasure_threshold)
            except DecodeError as exc:
                last_error = exc
            else:
                identity = np.eye(3, dtype=np.float64)
                diagnostics = RectificationDiagnostics(
                    ellipse=guard,
                    anchor_run_lengths=(),
                    anchor_source_points=(),
                    anchor_target_points=(),
                    homography=tuple(tuple(float(value) for value in row) for row in identity),
                    reprojection_error_px=0.0,
                    output_size=int(bgr.shape[0]),
                )
                return DetectedDecode(decoded=decoded, rectification=diagnostics)
            frontal = _frontal_rectification(bgr, guard, output_size)
            try:
                decoded = decode_canonical(frontal.image, erasure_threshold=erasure_threshold)
            except DecodeError as exc:
                last_error = exc
            else:
                return DetectedDecode(decoded=decoded, rectification=frontal.diagnostics)
    except DetectionError:
        pass
    try:
        fallback = _frontal_rectification(bgr, _dark_extent_guard_candidate(bgr), output_size)
        decoded = decode_canonical(fallback.image, erasure_threshold=erasure_threshold)
    except (DetectionError, DecodeError):
        pass
    else:
        return DetectedDecode(decoded=decoded, rectification=fallback.diagnostics)
    for rectified in _rectification_candidates(image, output_size=output_size):
        try:
            decoded = decode_canonical(rectified.image, erasure_threshold=erasure_threshold)
        except DecodeError as exc:
            last_error = exc
            continue
        return DetectedDecode(decoded=decoded, rectification=rectified.diagnostics)
    raise DetectionError("all rectification hypotheses completed but canonical decoding failed") from last_error
