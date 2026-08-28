"""Per-capture COLOR4 calibration and probabilistic classification."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Mapping, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class ColorClassification:
    symbol: int
    confidence: float
    second_symbol: int
    second_confidence: float
    probabilities: tuple[float, ...]
    mahalanobis_distances: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ColorModel:
    means: np.ndarray
    inverse_covariance: np.ndarray

    @property
    def states(self) -> int:
        return int(self.means.shape[0])

    def classify(self, rgb: Sequence[float]) -> ColorClassification:
        sample = np.asarray(rgb, dtype=np.float64)
        if sample.shape != (3,):
            raise ValueError("rgb sample must contain exactly three channels")
        deltas = self.means - sample
        distances = np.einsum("si,ij,sj->s", deltas, self.inverse_covariance, deltas)
        logits = -0.5 * distances
        logits -= np.max(logits)
        weights = np.exp(logits)
        probabilities = weights / np.sum(weights)
        ranking = np.argsort(-probabilities)
        best = int(ranking[0])
        second = int(ranking[1]) if len(ranking) > 1 else best
        return ColorClassification(
            symbol=best,
            confidence=float(probabilities[best]),
            second_symbol=second,
            second_confidence=float(probabilities[second]),
            probabilities=tuple(float(value) for value in probabilities),
            mahalanobis_distances=tuple(float(value) for value in distances),
        )

    def classify_many(self, rgb_samples: Sequence[Sequence[float]]) -> tuple[ColorClassification, ...]:
        samples = np.asarray(rgb_samples, dtype=np.float64)
        if samples.ndim != 2 or samples.shape[1] != 3:
            raise ValueError("rgb samples must have shape (n, 3)")
        if len(samples) == 0:
            return ()
        deltas = self.means[None, :, :] - samples[:, None, :]
        distances = np.einsum("nsi,ij,nsj->ns", deltas, self.inverse_covariance, deltas)
        logits = -0.5 * distances
        logits -= np.max(logits, axis=1, keepdims=True)
        weights = np.exp(logits)
        probabilities = weights / np.sum(weights, axis=1, keepdims=True)
        rankings = np.argsort(-probabilities, axis=1)
        output: list[ColorClassification] = []
        for index, ranking in enumerate(rankings):
            best = int(ranking[0])
            second = int(ranking[1]) if len(ranking) > 1 else best
            output.append(
                ColorClassification(
                    symbol=best,
                    confidence=float(probabilities[index, best]),
                    second_symbol=second,
                    second_confidence=float(probabilities[index, second]),
                    probabilities=tuple(float(value) for value in probabilities[index]),
                    mahalanobis_distances=tuple(float(value) for value in distances[index]),
                )
            )
        return tuple(output)


def fit_color_model(
    samples_by_state: Mapping[int, Sequence[Sequence[float]]],
    *,
    regularization: float = 25.0,
    robust: bool = False,
) -> ColorModel:
    if not samples_by_state:
        raise ValueError("at least one color state is required")
    states = sorted(samples_by_state)
    if states != list(range(len(states))):
        raise ValueError("color states must be contiguous and start at zero")

    groups: list[np.ndarray] = []
    means: list[np.ndarray] = []
    for state in states:
        group = np.asarray(samples_by_state[state], dtype=np.float64)
        if group.ndim != 2 or group.shape[1] != 3 or len(group) == 0:
            raise ValueError("each color state must provide one or more RGB samples")
        if robust and len(group) >= 3:
            median = np.median(group, axis=0)
            distances = np.linalg.norm(group - median, axis=1)
            distance_median = float(np.median(distances))
            median_absolute_deviation = float(np.median(np.abs(distances - distance_median)))
            # Four references per COLOR4 state are dispersed across rings. One
            # local obstruction should not drag their calibration toward black
            # or white. The floor retains ordinary raster/camera variation.
            cutoff = distance_median + 3.0 * max(median_absolute_deviation, 4.0)
            inliers = group[distances <= cutoff]
            if len(inliers) >= 2:
                group = inliers
        groups.append(group)
        means.append(np.median(group, axis=0) if robust else np.mean(group, axis=0))

    residuals = np.concatenate(
        [group - mean for group, mean in zip(groups, means, strict=True)],
        axis=0,
    )
    if len(residuals) > 1:
        covariance = (residuals.T @ residuals) / max(1, len(residuals) - len(groups))
    else:
        covariance = np.zeros((3, 3), dtype=np.float64)
    covariance += np.eye(3, dtype=np.float64) * regularization
    inverse = np.linalg.inv(covariance)
    return ColorModel(means=np.vstack(means), inverse_covariance=inverse)


def nominal_color_model(rgb_values: Sequence[Sequence[float]], *, regularization: float = 64.0) -> ColorModel:
    return fit_color_model(
        {state: [rgb] for state, rgb in enumerate(rgb_values)},
        regularization=regularization,
    )


def classification_erasure(classification: ColorClassification, *, threshold: float) -> bool:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between zero and one")
    return classification.confidence < threshold
