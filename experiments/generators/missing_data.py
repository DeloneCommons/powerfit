"""Synthetic generators and metrics for Experiment C.

Experiment C starts from an exact power-diagram instance whose realized-pair
graph is connected. It then removes a prescribed fraction of measured pair rows
and studies how the inverse fit loses *global* identifiability while remaining
exact on the connected components that survive.
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
)


@dataclass(frozen=True)
class MissingDataInstance:
    """One subsampled exact instance for Experiment C."""

    base: ExactRecoveryInstance
    observed_raw_constraints: list[tuple]
    observed_resolved_constraints: pyvoro2.PairBisectorConstraints
    keep_fraction_requested: float
    keep_fraction_actual: float
    observed_component_labels: np.ndarray
    observed_component_sizes: np.ndarray
    base_generation_attempts: int
    sampling_seed: int


@dataclass(frozen=True)
class MissingGraphMetrics:
    """Graph-structure diagnostics induced by the observed rows."""

    n_components: int
    connected: bool
    largest_component_fraction: float
    recoverable_pair_fraction: float
    isolated_site_fraction: float


@dataclass(frozen=True)
class MissingRecoveryMetrics:
    """Recovery diagnostics separating global and componentwise behavior."""

    componentwise_aligned_weight_rmse: float
    global_centered_weight_rmse: float
    all_pair_difference_rmse: float
    same_component_pair_difference_rmse: float
    component_shift_std: float


def _site_graph_labels(constraints: pyvoro2.PairBisectorConstraints) -> np.ndarray:
    edges = list(zip(constraints.i.tolist(), constraints.j.tolist(), strict=True))
    return component_labels(constraints.n_points, edges)


def _connected(labels: np.ndarray) -> bool:
    return bool(int(np.max(labels)) == 0)


def _subsample_raw_constraints(
    raw_constraints: list[tuple],
    *,
    keep_fraction: float,
    rng: np.random.Generator,
) -> tuple[list[tuple], np.ndarray]:
    if not (0.0 < float(keep_fraction) <= 1.0):
        raise ValueError('keep_fraction must lie in (0, 1]')
    n_constraints = len(raw_constraints)
    if n_constraints == 0:
        raise ValueError('cannot subsample an empty realized-pair list')

    n_keep = int(round(float(keep_fraction) * n_constraints))
    n_keep = max(1, min(n_constraints, n_keep))
    if n_keep == n_constraints:
        keep_idx = np.arange(n_constraints, dtype=int)
    else:
        keep_idx = np.sort(rng.choice(n_constraints, size=n_keep, replace=False))

    keep_mask = np.zeros(n_constraints, dtype=bool)
    keep_mask[keep_idx] = True
    subset = [raw_constraints[idx] for idx in keep_idx.tolist()]
    return subset, keep_mask


def make_connected_exact_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
    max_attempts: int = 50,
) -> tuple[ExactRecoveryInstance, int]:
    """Generate an exact instance whose full realized-pair graph is connected.

    Experiment C is about *loss* of identifiability caused by missing rows, so
    the baseline instance should start from a connected realized graph.
    """
    for attempt in range(int(max_attempts)):
        trial_seed = int(seed) + 1000003 * attempt
        instance = make_exact_recovery_instance(
            n_sites=n_sites,
            dim=dim,
            periodic=False,
            seed=trial_seed,
            graph_variant='full_realized',
            measurement=measurement,
            weight_scale=weight_scale,
            validate_periodic_planar_shifts=False,
        )
        labels = _site_graph_labels(instance.resolved_constraints)
        if _connected(labels):
            return instance, attempt + 1
    raise RuntimeError(
        'failed to generate a connected realized-pair graph '
        f'after {max_attempts} attempts (dim={dim}, n_sites={n_sites})'
    )


def make_missing_data_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    keep_fraction: float,
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
    max_base_generation_attempts: int = 50,
) -> MissingDataInstance:
    """Create one observed-row subsampling instance for Experiment C."""
    base, attempts = make_connected_exact_instance(
        n_sites=n_sites,
        dim=dim,
        seed=seed,
        measurement=measurement,
        weight_scale=weight_scale,
        max_attempts=max_base_generation_attempts,
    )
    rng = np.random.default_rng(seed ^ 0xD1B54A32D192ED03)
    observed_raw_constraints, _keep_mask = _subsample_raw_constraints(
        base.raw_constraints,
        keep_fraction=keep_fraction,
        rng=rng,
    )
    observed = pyvoro2.resolve_pair_bisector_constraints(
        base.points,
        observed_raw_constraints,
        measurement=measurement,
        domain=base.domain,
        image='nearest',
    )
    labels = _site_graph_labels(observed)
    counts = np.bincount(labels, minlength=int(np.max(labels)) + 1)
    return MissingDataInstance(
        base=base,
        observed_raw_constraints=observed_raw_constraints,
        observed_resolved_constraints=observed,
        keep_fraction_requested=float(keep_fraction),
        keep_fraction_actual=float(len(observed_raw_constraints) / len(base.raw_constraints)),
        observed_component_labels=labels,
        observed_component_sizes=counts,
        base_generation_attempts=int(attempts),
        sampling_seed=int(seed ^ 0xD1B54A32D192ED03),
    )


def graph_metrics(labels: np.ndarray) -> MissingGraphMetrics:
    """Return component-structure diagnostics for the observed row graph."""
    labels = np.asarray(labels, dtype=int)
    if labels.size == 0:
        raise ValueError('labels must be non-empty')
    counts = np.bincount(labels, minlength=int(np.max(labels)) + 1)
    n_sites = int(np.sum(counts))
    n_components = int(len(counts))
    largest_component_fraction = float(np.max(counts) / n_sites)
    total_pairs = n_sites * (n_sites - 1) // 2
    recoverable_pairs = int(np.sum(counts * (counts - 1) // 2))
    recoverable_pair_fraction = 1.0 if total_pairs == 0 else float(recoverable_pairs / total_pairs)
    isolated_site_fraction = float(np.sum(counts == 1) / n_sites)
    return MissingGraphMetrics(
        n_components=n_components,
        connected=(n_components == 1),
        largest_component_fraction=largest_component_fraction,
        recoverable_pair_fraction=recoverable_pair_fraction,
        isolated_site_fraction=isolated_site_fraction,
    )


def global_centered_weight_rmse(true_weights: np.ndarray, fit_weights: np.ndarray) -> float:
    """Best single-gauge alignment RMSE over all sites."""
    true_arr = np.asarray(true_weights, dtype=float)
    fit_arr = np.asarray(fit_weights, dtype=float)
    shift = float(np.mean(fit_arr - true_arr))
    aligned = fit_arr - shift
    return float(np.sqrt(np.mean((aligned - true_arr) ** 2)))


def _pair_difference_errors(true_weights: np.ndarray, fit_weights: np.ndarray) -> np.ndarray:
    true_arr = np.asarray(true_weights, dtype=float)
    fit_arr = np.asarray(fit_weights, dtype=float)
    i_idx, j_idx = np.triu_indices(true_arr.shape[0], k=1)
    return (fit_arr[i_idx] - fit_arr[j_idx]) - (true_arr[i_idx] - true_arr[j_idx])


def all_pair_difference_rmse(true_weights: np.ndarray, fit_weights: np.ndarray) -> float:
    """RMSE of weight differences over all site pairs."""
    errors = _pair_difference_errors(true_weights, fit_weights)
    if errors.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(errors * errors)))


def same_component_pair_difference_rmse(
    true_weights: np.ndarray,
    fit_weights: np.ndarray,
    labels: np.ndarray,
) -> float:
    """RMSE of weight differences restricted to theoretically recoverable pairs."""
    labels_arr = np.asarray(labels, dtype=int)
    i_idx, j_idx = np.triu_indices(labels_arr.shape[0], k=1)
    same_mask = labels_arr[i_idx] == labels_arr[j_idx]
    if not np.any(same_mask):
        return float('nan')
    errors = _pair_difference_errors(true_weights, fit_weights)[same_mask]
    return float(np.sqrt(np.mean(errors * errors)))


def component_shift_std(true_weights: np.ndarray, fit_weights: np.ndarray, labels: np.ndarray) -> float:
    """Size-weighted standard deviation of optimal per-component shifts."""
    true_arr = np.asarray(true_weights, dtype=float)
    fit_arr = np.asarray(fit_weights, dtype=float)
    labels_arr = np.asarray(labels, dtype=int)
    shifts: list[float] = []
    weights: list[int] = []
    for comp in np.unique(labels_arr):
        mask = labels_arr == comp
        shifts.append(float(np.mean(fit_arr[mask] - true_arr[mask])))
        weights.append(int(np.sum(mask)))
    shift_arr = np.asarray(shifts, dtype=float)
    weight_arr = np.asarray(weights, dtype=float)
    mean_shift = float(np.average(shift_arr, weights=weight_arr))
    return float(math.sqrt(np.average((shift_arr - mean_shift) ** 2, weights=weight_arr)))


def recovery_metrics(
    true_weights: np.ndarray,
    fit_weights: np.ndarray,
    labels: np.ndarray,
) -> MissingRecoveryMetrics:
    """Return the Experiment C recovery diagnostics."""
    labels_arr = np.asarray(labels, dtype=int)
    return MissingRecoveryMetrics(
        componentwise_aligned_weight_rmse=componentwise_aligned_rmse(true_weights, fit_weights, labels_arr),
        global_centered_weight_rmse=global_centered_weight_rmse(true_weights, fit_weights),
        all_pair_difference_rmse=all_pair_difference_rmse(true_weights, fit_weights),
        same_component_pair_difference_rmse=same_component_pair_difference_rmse(true_weights, fit_weights, labels_arr),
        component_shift_std=component_shift_std(true_weights, fit_weights, labels_arr),
    )
