"""Deterministic synthetic degradation harness for RadialCode images."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import sqrt

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


@dataclass(frozen=True, slots=True)
class Degradation:
    blur_radius: float = 0.0
    noise_sigma: float = 0.0
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    jpeg_quality: int = 100
    downsample_factor: float = 1.0
    occlusion_fraction: float = 0.0
    seed: int = 1

    def validate(self) -> None:
        if self.blur_radius < 0:
            raise ValueError("blur_radius must not be negative")
        if self.noise_sigma < 0:
            raise ValueError("noise_sigma must not be negative")
        if self.brightness <= 0 or self.contrast <= 0 or self.saturation < 0:
            raise ValueError("brightness and contrast must be positive; saturation must be nonnegative")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if not 0 < self.downsample_factor <= 1:
            raise ValueError("downsample_factor must be in (0, 1]")
        if not 0 <= self.occlusion_fraction < 0.5:
            raise ValueError("occlusion_fraction must be in [0, 0.5)")



def _to_rgb(image: Image.Image | bytes) -> Image.Image:
    if isinstance(image, bytes):
        image = Image.open(BytesIO(image))
    if not isinstance(image, Image.Image):
        raise TypeError("image must be PNG bytes or a PIL Image")
    if image.mode == "RGBA":
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        return background.convert("RGB")
    return image.convert("RGB")


def degrade(image: Image.Image | bytes, profile: Degradation) -> Image.Image:
    """Apply a synthetic degradation profile in a fixed, documented order."""

    profile.validate()
    output = _to_rgb(image)
    original_size = output.size

    if profile.downsample_factor < 1.0:
        reduced = (
            max(1, int(round(output.width * profile.downsample_factor))),
            max(1, int(round(output.height * profile.downsample_factor))),
        )
        output = output.resize(reduced, Image.Resampling.LANCZOS)
        output = output.resize(original_size, Image.Resampling.BICUBIC)

    if profile.blur_radius > 0:
        output = output.filter(ImageFilter.GaussianBlur(profile.blur_radius))
    if profile.brightness != 1.0:
        output = ImageEnhance.Brightness(output).enhance(profile.brightness)
    if profile.contrast != 1.0:
        output = ImageEnhance.Contrast(output).enhance(profile.contrast)
    if profile.saturation != 1.0:
        output = ImageEnhance.Color(output).enhance(profile.saturation)

    if profile.noise_sigma > 0:
        rng = np.random.default_rng(profile.seed)
        array = np.asarray(output, dtype=np.float64)
        noise = rng.normal(0.0, profile.noise_sigma, size=array.shape)
        output = Image.fromarray(np.clip(array + noise, 0, 255).astype(np.uint8), mode="RGB")

    if profile.occlusion_fraction > 0:
        rng = np.random.default_rng(profile.seed ^ 0x5A17)
        target_area = output.width * output.height * profile.occlusion_fraction
        side = max(1, int(round(sqrt(target_area))))
        center_x = int(round(output.width * float(rng.uniform(0.28, 0.72))))
        center_y = int(round(output.height * float(rng.uniform(0.28, 0.72))))
        box = (
            max(0, center_x - side // 2),
            max(0, center_y - side // 2),
            min(output.width - 1, center_x + side // 2),
            min(output.height - 1, center_y + side // 2),
        )
        fill = (255, 255, 255) if int(rng.integers(0, 2)) else (18, 18, 18)
        ImageDraw.Draw(output).rounded_rectangle(box, radius=max(1, side // 8), fill=fill)

    if profile.jpeg_quality < 100:
        buffer = BytesIO()
        output.save(buffer, format="JPEG", quality=profile.jpeg_quality, optimize=False, progressive=False)
        buffer.seek(0)
        output = Image.open(buffer).convert("RGB")

    return output


def project_to_scene(
    image: Image.Image | bytes,
    *,
    corners: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
    canvas_size: tuple[int, int] = (1000, 800),
    background: tuple[int, int, int] = (225, 225, 225),
) -> Image.Image:
    """Project a canonical symbol into a larger scene using four pixel corners.

    Corner order is top-left, top-right, bottom-right and bottom-left.
    """

    source_image = _to_rgb(image)
    source = np.float32(
        [
            (0.0, 0.0),
            (source_image.width - 1.0, 0.0),
            (source_image.width - 1.0, source_image.height - 1.0),
            (0.0, source_image.height - 1.0),
        ]
    )
    destination = np.float32(corners)
    if destination.shape != (4, 2):
        raise ValueError("corners must contain four (x, y) pairs")
    width, height = canvas_size
    if width <= 0 or height <= 0:
        raise ValueError("canvas_size must be positive")

    transform = cv2.getPerspectiveTransform(source, destination)
    rgb = np.asarray(source_image, dtype=np.uint8)
    warped = cv2.warpPerspective(
        rgb,
        transform,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=background,
    )
    mask_source = np.full((source_image.height, source_image.width), 255, dtype=np.uint8)
    mask = cv2.warpPerspective(
        mask_source,
        transform,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[:] = background
    canvas[mask > 0] = warped[mask > 0]
    return Image.fromarray(canvas, mode="RGB")
