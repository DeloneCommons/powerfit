"""Synthetic generators for Experiment G: structured model mismatch.

This module keeps the benchmark-specific surrogate-law logic in the paper repo
while delegating all inverse fitting and tessellation computation to
:mod:`pyvoro2`.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np
import pyvoro2

from experiments.generators.exact_recovery import (
    _raw_realized_pairs_from_cells,
    make_domain,
    sample_power_weights,
)


@dataclass(frozen=True)
class ModelMismatchInstance:
    """One structured model-mismatch benchmark instance."""

    points: np.ndarray
    true_weights: np.ndarray
    radii: np.ndarray
    domain: Any
    exact_raw_constraints: list[tuple[int, int, float]]
    exact_constraints: pyvoro2.PairBisectorConstraints
    observed_constraints: pyvoro2.PairBisectorConstraints
    exact_target: np.ndarray
    observed_target: np.ndarray
    type_labels: np.ndarray
    local_context: np.ndarray
    geometry_family: str
    law_family: str
    eta: float
    seed: int
    clip_fraction: float


def _minimum_distance_scale(n_sites: int, dim: int, family: str) -> float:
    base = float(n_sites) ** (-1.0 / float(dim))
    if family == 'hard_core_random':
        return 0.34 * base
    if family == 'perturbed_lattice':
        return 0.22 * base
    raise ValueError(f'unsupported geometry family: {family}')


def _pairwise_distances(points: np.ndarray) -> np.ndarray:
    delta = points[:, None, :] - points[None, :, :]
    dist = np.sqrt(np.sum(delta * delta, axis=2))
    np.fill_diagonal(dist, np.inf)
    return dist


def _hard_core_points(
    n_sites: int,
    dim: int,
    rng: np.random.Generator,
    *,
    min_distance: float,
    max_attempts: int = 200_000,
) -> np.ndarray:
    points = np.empty((n_sites, dim), dtype=float)
    n_accept = 0
    attempts = 0
    while n_accept < n_sites:
        if attempts >= max_attempts:
            raise RuntimeError(
                f'failed to sample {n_sites} hard-core points in {dim}D '
                f'with min_distance={min_distance:.4f}'
            )
        candidate = rng.random(dim, dtype=float)
        if n_accept == 0:
            points[n_accept] = candidate
            n_accept += 1
            attempts += 1
            continue
        delta = points[:n_accept] - candidate[None, :]
        dist2 = np.sum(delta * delta, axis=1)
        if np.all(dist2 >= min_distance * min_distance):
            points[n_accept] = candidate
            n_accept += 1
        attempts += 1
    return points


def _balanced_grid_counts(n_sites: int, dim: int) -> tuple[int, ...]:
    root = max(2, int(round(n_sites ** (1.0 / dim))))
    candidate_ranges = [range(max(2, root - 2), root + 4) for _ in range(dim)]
    best_counts: tuple[int, ...] | None = None
    best_score: tuple[float, float, int] | None = None
    for counts in product(*candidate_ranges):
        total = int(np.prod(counts))
        if total < n_sites:
            continue
        spread = np.log(max(counts) / min(counts)) if max(counts) > min(counts) else 0.0
        density_gap = (total / n_sites) - 1.0
        score = (density_gap + 0.45 * spread, spread, total)
        if best_score is None or score < best_score:
            best_score = score
            best_counts = tuple(int(v) for v in counts)
    if best_counts is None:
        raise RuntimeError(f'failed to build grid counts for n_sites={n_sites}, dim={dim}')
    return best_counts


def _perturbed_lattice_points(
    n_sites: int,
    dim: int,
    rng: np.random.Generator,
    *,
    min_distance: float,
    jitter_fraction: float = 0.18,
) -> np.ndarray:
    counts = _balanced_grid_counts(n_sites, dim)
    axes = [np.linspace(0.5 / c, 1.0 - 0.5 / c, c) for c in counts]
    mesh = np.meshgrid(*axes, indexing='ij')
    grid = np.column_stack([m.reshape(-1) for m in mesh])
    if len(grid) < n_sites:
        raise RuntimeError('internal lattice grid underfilled unexpectedly')

    if len(grid) > n_sites:
        center = np.full(dim, 0.5, dtype=float)
        dist_center = np.sum((grid - center[None, :]) ** 2, axis=1)
        order = np.argsort(dist_center)
        grid = grid[order[:n_sites]].copy()
    else:
        grid = grid.copy()

    cell_spacing = np.array([1.0 / c for c in counts], dtype=float)
    jitter_scale = jitter_fraction * float(np.min(cell_spacing))
    jitter = rng.normal(loc=0.0, scale=jitter_scale, size=grid.shape)
    points = np.clip(grid + jitter, 0.02, 0.98)

    # Light rejection/repair if the jitter creates too-close neighbours.
    for _ in range(6):
        dist = _pairwise_distances(points)
        bad_i, bad_j = np.where(dist < min_distance)
        if len(bad_i) == 0:
            return points
        moved = set()
        for i, j in zip(bad_i.tolist(), bad_j.tolist(), strict=True):
            if i >= j or j in moved:
                continue
            moved.add(j)
            points[j] = np.clip(grid[j] + rng.normal(loc=0.0, scale=jitter_scale, size=dim), 0.02, 0.98)
    return points


def sample_geometry_points(
    *,
    n_sites: int,
    dim: int,
    geometry_family: str,
    rng: np.random.Generator,
) -> np.ndarray:
    min_distance = _minimum_distance_scale(n_sites, dim, geometry_family)
    if geometry_family == 'hard_core_random':
        return _hard_core_points(n_sites, dim, rng, min_distance=min_distance)
    if geometry_family == 'perturbed_lattice':
        return _perturbed_lattice_points(n_sites, dim, rng, min_distance=min_distance)
    raise ValueError(f'unsupported geometry family: {geometry_family}')


def _resolve_fraction_constraints(
    points: np.ndarray,
    rows: list[tuple[int, int, float]],
    *,
    domain: Any,
) -> pyvoro2.PairBisectorConstraints:
    return pyvoro2.resolve_pair_bisector_constraints(
        points,
        rows,
        measurement='fraction',
        domain=domain,
        image='nearest',
    )


def _sample_type_labels(n_sites: int, n_types: int, rng: np.random.Generator) -> np.ndarray:
    if n_types < 2:
        raise ValueError('n_types must be at least 2')
    while True:
        labels = rng.integers(0, n_types, size=n_sites, endpoint=False)
        if len(np.unique(labels)) == n_types:
            return labels.astype(int)


def _local_context_scores(points: np.ndarray, *, k_neighbors: int) -> np.ndarray:
    dist = _pairwise_distances(points)
    k = max(1, min(int(k_neighbors), len(points) - 1))
    mean_nn = np.mean(np.sort(dist, axis=1)[:, :k], axis=1)
    crowding = -mean_nn
    crowding -= float(np.mean(crowding))
    denom = float(np.std(crowding))
    if denom <= 1.0e-12:
        return np.zeros_like(crowding)
    return crowding / denom


def _type_cycle_delta(
    constraints: pyvoro2.PairBisectorConstraints,
    *,
    type_labels: np.ndarray,
    eta: float,
) -> np.ndarray:
    if eta == 0.0:
        return np.zeros(constraints.n_constraints, dtype=float)
    bmat = np.array(
        [
            [0.0, 1.0, -1.0],
            [-1.0, 0.0, 1.0],
            [1.0, -1.0, 0.0],
        ],
        dtype=float,
    )
    dist = np.asarray(constraints.distance, dtype=float)
    scale = float(np.median(dist))
    scale = max(scale, 1.0e-8)
    phi = np.exp(-0.5 * (((dist / scale) - 1.0) / 0.55) ** 2)
    pair_bias = bmat[type_labels[constraints.i], type_labels[constraints.j]]
    return float(eta) * pair_bias * phi


def _local_context_delta(
    constraints: pyvoro2.PairBisectorConstraints,
    *,
    local_context: np.ndarray,
    eta: float,
) -> np.ndarray:
    if eta == 0.0:
        return np.zeros(constraints.n_constraints, dtype=float)
    dist = np.asarray(constraints.distance, dtype=float)
    scale = float(np.median(dist))
    scale = max(scale, 1.0e-8)
    psi = 1.0 / (1.0 + (dist / scale) ** 2)
    contrast = np.tanh(0.75 * (local_context[constraints.i] - local_context[constraints.j]))
    return float(eta) * contrast * psi


def observed_targets(
    exact_constraints: pyvoro2.PairBisectorConstraints,
    *,
    law_family: str,
    eta: float,
    type_labels: np.ndarray,
    local_context: np.ndarray,
    clip_interval: tuple[float, float],
) -> tuple[np.ndarray, float]:
    exact_target = np.asarray(exact_constraints.target, dtype=float)
    if law_family == 'exact_control':
        raw = exact_target.copy()
    elif law_family == 'type_cycle':
        raw = exact_target + _type_cycle_delta(
            exact_constraints,
            type_labels=type_labels,
            eta=eta,
        )
    elif law_family == 'local_context':
        raw = exact_target + _local_context_delta(
            exact_constraints,
            local_context=local_context,
            eta=eta,
        )
    else:
        raise ValueError(f'unsupported law family: {law_family}')

    base_lower, base_upper = (float(clip_interval[0]), float(clip_interval[1]))
    lower = np.minimum(exact_target, base_lower)
    upper = np.maximum(exact_target, base_upper)
    clipped = np.minimum(np.maximum(raw, lower), upper)
    clip_fraction = float(np.mean(np.abs(clipped - raw) > 1.0e-15))
    return clipped, clip_fraction


def make_model_mismatch_instance(
    *,
    n_sites: int,
    dim: int,
    geometry_family: str,
    law_family: str,
    eta: float,
    seed: int,
    weight_scale: float = 0.08,
    n_types: int = 3,
    k_neighbors: int = 4,
    clip_interval: tuple[float, float] = (0.05, 0.95),
) -> ModelMismatchInstance:
    rng = np.random.default_rng(seed)
    points = sample_geometry_points(
        n_sites=n_sites,
        dim=dim,
        geometry_family=geometry_family,
        rng=rng,
    )
    domain = make_domain(dim, periodic=False)
    true_weights, radii = sample_power_weights(points, periodic=False, rng=rng, weight_scale=weight_scale)
    exact_raw_constraints = _raw_realized_pairs_from_cells(
        points,
        true_weights,
        domain,
        dim=dim,
        periodic=False,
        measurement='fraction',
        validate_periodic_planar_shifts=False,
    )
    exact_constraints = _resolve_fraction_constraints(points, exact_raw_constraints, domain=domain)

    type_labels = _sample_type_labels(n_sites, n_types, rng)
    local_context = _local_context_scores(points, k_neighbors=k_neighbors)
    observed_target, clip_fraction = observed_targets(
        exact_constraints,
        law_family=law_family,
        eta=eta,
        type_labels=type_labels,
        local_context=local_context,
        clip_interval=clip_interval,
    )
    observed_rows = [
        (int(i), int(j), float(y))
        for i, j, y in zip(exact_constraints.i.tolist(), exact_constraints.j.tolist(), observed_target.tolist(), strict=True)
    ]
    observed_constraints = _resolve_fraction_constraints(points, observed_rows, domain=domain)

    return ModelMismatchInstance(
        points=points,
        true_weights=true_weights,
        radii=radii,
        domain=domain,
        exact_raw_constraints=exact_raw_constraints,
        exact_constraints=exact_constraints,
        observed_constraints=observed_constraints,
        exact_target=np.asarray(exact_constraints.target, dtype=float).copy(),
        observed_target=np.asarray(observed_constraints.target, dtype=float).copy(),
        type_labels=type_labels,
        local_context=local_context,
        geometry_family=geometry_family,
        law_family=law_family,
        eta=float(eta),
        seed=int(seed),
        clip_fraction=clip_fraction,
    )
