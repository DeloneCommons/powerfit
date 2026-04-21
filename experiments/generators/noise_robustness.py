"""Synthetic generators for noise-robustness benchmarks.

This benchmark starts from an exact power-diagram instance and perturbs the
pairwise separator observations in measurement space. The core inverse fitting
remains in :mod:`pyvoro2`; this module owns benchmark generation
and derived metrics for the paper repo.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pyvoro2

from experiments.generators.exact_recovery import (
    ExactRecoveryInstance,
    component_labels,
    componentwise_aligned_rmse,
    make_exact_recovery_instance,
    pair_difference_rmse,
)


@dataclass(frozen=True)
class NoiseRobustnessInstance:
    """One noisy benchmark instance built from an exact power diagram."""

    base: ExactRecoveryInstance
    clean_resolved_constraints: pyvoro2.PairBisectorConstraints
    noisy_raw_constraints: list[tuple]
    noisy_resolved_constraints: pyvoro2.PairBisectorConstraints
    clean_target: np.ndarray
    noisy_target: np.ndarray
    injected_noise: np.ndarray
    noise_family: str
    sigma: float
    outlier_fraction: float
    outlier_amplitude: float
    outlier_mask: np.ndarray
    seed: int


@dataclass(frozen=True)
class AlgebraicResidualMetrics:
    """Residual metrics in edge-difference space."""

    z_obs: np.ndarray
    z_fit: np.ndarray
    weighted_l2: float
    weighted_rmse: float
    unweighted_rmse: float
    unweighted_mae: float


@dataclass(frozen=True)
class WeightRecoveryMetrics:
    """Gauge-aware recovery errors against the true weights."""

    edge_difference_rmse: float
    centered_weight_rmse: float


@dataclass(frozen=True)
class MeasurementRecoveryMetrics:
    """Measurement-space recovery errors against clean and noisy observations."""

    clean_rmse: float
    clean_mae: float
    noisy_rmse: float
    noisy_mae: float


@dataclass(frozen=True)
class NoiseDescriptor:
    """Resolved synthetic noise condition."""

    family: str
    sigma: float
    outlier_fraction: float = 0.0
    outlier_amplitude: float = 0.0

    @property
    def level(self) -> float:
        if self.family == 'outlier':
            return float(self.outlier_amplitude)
        return float(self.sigma)

    @property
    def label(self) -> str:
        if self.family == 'outlier':
            return f'outlier_amp_{self.outlier_amplitude:g}'
        return f'{self.family}_sigma_{self.sigma:g}'


def _replace_constraint_targets(raw_constraints: list[tuple], targets: np.ndarray) -> list[tuple]:
    """Replace measurement values in raw constraint tuples.

    The raw tuple schema is either ``(i, j, value)`` or ``(i, j, value, shift)``.
    """
    if len(raw_constraints) != int(targets.shape[0]):
        raise ValueError('target vector length does not match raw constraints')
    out: list[tuple] = []
    for row, value in zip(raw_constraints, targets.tolist(), strict=True):
        if len(row) == 3:
            i, j, _old = row
            out.append((int(i), int(j), float(value)))
        elif len(row) == 4:
            i, j, _old, shift = row
            out.append((int(i), int(j), float(value), tuple(int(v) for v in shift)))
        else:
            raise ValueError(f'unsupported raw constraint row: {row!r}')
    return out


def _sample_noise(
    n_constraints: int,
    descriptor: NoiseDescriptor,
    *,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw measurement-space noise and an outlier mask."""
    family = descriptor.family
    sigma = float(descriptor.sigma)
    if sigma < 0.0:
        raise ValueError('sigma must be >= 0')

    if family == 'gaussian':
        noise = rng.normal(loc=0.0, scale=sigma, size=n_constraints)
        outlier_mask = np.zeros(n_constraints, dtype=bool)
        return noise.astype(float), outlier_mask

    if family == 'laplace':
        scale = sigma / math.sqrt(2.0)
        noise = rng.laplace(loc=0.0, scale=scale, size=n_constraints)
        outlier_mask = np.zeros(n_constraints, dtype=bool)
        return noise.astype(float), outlier_mask

    if family == 'outlier':
        base = rng.normal(loc=0.0, scale=sigma, size=n_constraints)
        outlier_fraction = float(descriptor.outlier_fraction)
        outlier_amplitude = float(descriptor.outlier_amplitude)
        if not (0.0 <= outlier_fraction <= 1.0):
            raise ValueError('outlier_fraction must lie in [0, 1]')
        if outlier_amplitude < 0.0:
            raise ValueError('outlier_amplitude must be >= 0')
        n_outliers = int(round(outlier_fraction * n_constraints))
        n_outliers = max(0, min(n_constraints, n_outliers))
        mask = np.zeros(n_constraints, dtype=bool)
        if n_outliers > 0:
            picked = rng.choice(n_constraints, size=n_outliers, replace=False)
            mask[picked] = True
            signs = rng.choice(np.array([-1.0, 1.0], dtype=float), size=n_outliers)
            base[picked] += signs * outlier_amplitude
        return base.astype(float), mask

    raise ValueError(f'unsupported noise family: {family}')


def make_noise_robustness_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    descriptor: NoiseDescriptor,
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
) -> NoiseRobustnessInstance:
    """Create one noisy synthetic instance for Experiment B."""
    base = make_exact_recovery_instance(
        n_sites=n_sites,
        dim=dim,
        periodic=False,
        seed=seed,
        graph_variant='full_realized',
        measurement=measurement,
        weight_scale=weight_scale,
        validate_periodic_planar_shifts=False,
    )
    clean_constraints = base.resolved_constraints
    clean_target = np.asarray(clean_constraints.target, dtype=float)

    rng = np.random.default_rng(seed ^ 0x9E3779B97F4A7C15)
    noise, outlier_mask = _sample_noise(clean_constraints.n_constraints, descriptor, rng=rng)
    noisy_target = clean_target + noise
    noisy_raw_constraints = _replace_constraint_targets(base.raw_constraints, noisy_target)
    noisy_constraints = pyvoro2.resolve_pair_bisector_constraints(
        base.points,
        noisy_raw_constraints,
        measurement=measurement,
        domain=base.domain,
        image='nearest',
    )

    return NoiseRobustnessInstance(
        base=base,
        clean_resolved_constraints=clean_constraints,
        noisy_raw_constraints=noisy_raw_constraints,
        noisy_resolved_constraints=noisy_constraints,
        clean_target=clean_target,
        noisy_target=np.asarray(noisy_constraints.target, dtype=float),
        injected_noise=noise,
        noise_family=descriptor.family,
        sigma=float(descriptor.sigma),
        outlier_fraction=float(descriptor.outlier_fraction),
        outlier_amplitude=float(descriptor.outlier_amplitude),
        outlier_mask=outlier_mask,
        seed=seed,
    )


def component_labels_for_constraints(constraints: pyvoro2.PairBisectorConstraints) -> np.ndarray:
    """Return connected-component labels for a constraint graph."""
    edges = list(zip(constraints.i.tolist(), constraints.j.tolist(), strict=True))
    return component_labels(constraints.n_points, edges)


def weight_recovery_metrics(
    true_weights: np.ndarray,
    fit_weights: np.ndarray,
    constraints: pyvoro2.PairBisectorConstraints,
) -> WeightRecoveryMetrics:
    """Gauge-aware weight recovery metrics."""
    labels = component_labels_for_constraints(constraints)
    return WeightRecoveryMetrics(
        edge_difference_rmse=pair_difference_rmse(true_weights, fit_weights, constraints),
        centered_weight_rmse=componentwise_aligned_rmse(true_weights, fit_weights, labels),
    )


def measurement_recovery_metrics(
    clean_target: np.ndarray,
    noisy_target: np.ndarray,
    predicted: np.ndarray,
) -> MeasurementRecoveryMetrics:
    """Recovery metrics in the chosen measurement space."""
    clean_residual = np.asarray(predicted, dtype=float) - np.asarray(clean_target, dtype=float)
    noisy_residual = np.asarray(predicted, dtype=float) - np.asarray(noisy_target, dtype=float)
    return MeasurementRecoveryMetrics(
        clean_rmse=float(np.sqrt(np.mean(clean_residual * clean_residual))),
        clean_mae=float(np.mean(np.abs(clean_residual))),
        noisy_rmse=float(np.sqrt(np.mean(noisy_residual * noisy_residual))),
        noisy_mae=float(np.mean(np.abs(noisy_residual))),
    )


def measurement_geometry(constraints: pyvoro2.PairBisectorConstraints) -> tuple[np.ndarray, np.ndarray]:
    """Return the affine coefficients ``y = beta + alpha (w_i - w_j)``."""
    if constraints.measurement == 'fraction':
        alpha = 1.0 / (2.0 * np.asarray(constraints.distance2, dtype=float))
        beta = np.full(constraints.n_constraints, 0.5, dtype=float)
        return alpha, beta
    if constraints.measurement == 'position':
        dist = np.asarray(constraints.distance, dtype=float)
        alpha = 1.0 / (2.0 * dist)
        beta = 0.5 * dist
        return alpha, beta
    raise ValueError(f'unsupported measurement: {constraints.measurement}')


def algebraic_residual_metrics(
    constraints: pyvoro2.PairBisectorConstraints,
    fit_weights: np.ndarray,
) -> AlgebraicResidualMetrics:
    """Return residual metrics in edge-difference space."""
    alpha, beta = measurement_geometry(constraints)
    z_obs = (np.asarray(constraints.target, dtype=float) - beta) / alpha
    z_fit = np.asarray(fit_weights, dtype=float)[constraints.i] - np.asarray(fit_weights, dtype=float)[constraints.j]
    residual = z_obs - z_fit
    rho = np.asarray(constraints.confidence, dtype=float) * (alpha * alpha)
    weighted_l2 = float(np.linalg.norm(np.sqrt(rho) * residual))
    weighted_rmse = float(np.sqrt(np.mean(rho * residual * residual)))
    unweighted_rmse = float(np.sqrt(np.mean(residual * residual)))
    unweighted_mae = float(np.mean(np.abs(residual)))
    return AlgebraicResidualMetrics(
        z_obs=z_obs,
        z_fit=z_fit,
        weighted_l2=weighted_l2,
        weighted_rmse=weighted_rmse,
        unweighted_rmse=unweighted_rmse,
        unweighted_mae=unweighted_mae,
    )


def noisy_out_of_segment_rate(noisy_target: np.ndarray) -> float:
    """Fraction of fraction-space targets outside the segment [0, 1]."""
    arr = np.asarray(noisy_target, dtype=float)
    return float(np.mean((arr < 0.0) | (arr > 1.0)))

