"""Synthetic generators and metrics for Experiment E.

Experiment E is not about fitting on an oracle graph. It is about starting from
an *overcomplete candidate row set* and asking whether a realization-aware
active-set loop improves over a single fit-plus-check pass.

To isolate that question cleanly, synthetic instances are built as follows:

- start from an exact non-periodic power-diagram instance and its realized-pair
  graph;
- augment that graph with nearby extra pairs (kNN or radius based) so that the
  candidate graph is a strict supergraph;
- keep the exact or mildly perturbed separator data on true realized rows;
- assign a simple midpoint-like surrogate separator value to the extra rows.

The extra rows are therefore plausible candidate boundaries, but they are *not*
an oracle encoding of the true power weights. This is the regime where the
self-consistent refinement loop can reveal a nontrivial algorithmic gain.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pyvoro2

from experiments.generators.exact_recovery import ExactRecoveryInstance, make_exact_recovery_instance


@dataclass(frozen=True)
class ActiveSetInstance:
    """One supergraph-input instance for Experiment E."""

    base: ExactRecoveryInstance
    candidate_graph: str
    candidate_parameter: float
    extra_row_model: str
    candidate_raw_constraints: list[tuple[int, int, float]]
    candidate_constraints: pyvoro2.PairBisectorConstraints
    candidate_edges: tuple[tuple[int, int], ...]
    true_realized_edges: tuple[tuple[int, int], ...]
    true_realized_mask: np.ndarray
    true_target: np.ndarray
    observed_target: np.ndarray
    extra_pair_count: int
    candidate_pair_count: int
    true_pair_count: int
    candidate_pair_precision: float
    candidate_pair_recall: float
    candidate_pair_f1: float
    true_row_noise_sigma: float
    extra_row_noise_sigma: float
    seed: int


@dataclass(frozen=True)
class BinaryMaskMetrics:
    """Precision/recall/F1 for a selected candidate-row mask."""

    n_selected: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


def _pair_measurement(
    points: np.ndarray,
    weights: np.ndarray,
    i: int,
    j: int,
    *,
    measurement: str,
) -> float:
    delta = np.asarray(points[j], dtype=float) - np.asarray(points[i], dtype=float)
    d2 = float(delta @ delta)
    if d2 <= 0.0:
        raise ValueError('encountered non-positive connector length')
    fraction = 0.5 + float((weights[i] - weights[j]) / (2.0 * d2))
    if measurement == 'fraction':
        return float(fraction)
    if measurement == 'position':
        return float(math.sqrt(d2) * fraction)
    raise ValueError(f'unsupported measurement: {measurement}')


def _symmetric_knn_edges(points: np.ndarray, k: int) -> set[tuple[int, int]]:
    points_arr = np.asarray(points, dtype=float)
    n_points = int(points_arr.shape[0])
    d2 = np.sum((points_arr[:, None, :] - points_arr[None, :, :]) ** 2, axis=2)
    np.fill_diagonal(d2, np.inf)
    edges: set[tuple[int, int]] = set()
    for i in range(n_points):
        neighbors = np.argsort(d2[i])[: int(k)]
        for j in neighbors.tolist():
            a, b = sorted((int(i), int(j)))
            if a != b:
                edges.add((a, b))
    return edges


def _radius_edges(points: np.ndarray, radius_factor: float) -> set[tuple[int, int]]:
    points_arr = np.asarray(points, dtype=float)
    n_points = int(points_arr.shape[0])
    d2 = np.sum((points_arr[:, None, :] - points_arr[None, :, :]) ** 2, axis=2)
    np.fill_diagonal(d2, np.inf)
    nearest = np.sqrt(np.min(d2, axis=1))
    radius = float(radius_factor * np.median(nearest))
    dist = np.sqrt(d2)
    edges: set[tuple[int, int]] = set()
    for i in range(n_points):
        for j in range(i + 1, n_points):
            if float(dist[i, j]) <= radius:
                edges.add((int(i), int(j)))
    return edges


def _candidate_edge_set(
    points: np.ndarray,
    true_realized_edges: set[tuple[int, int]],
    *,
    candidate_graph: str,
    candidate_parameter: float,
) -> set[tuple[int, int]]:
    if candidate_graph == 'knn_supergraph':
        extra = _symmetric_knn_edges(points, int(round(candidate_parameter)))
    elif candidate_graph == 'radius_supergraph':
        extra = _radius_edges(points, float(candidate_parameter))
    else:
        raise ValueError(f'unsupported candidate_graph: {candidate_graph}')
    return set(true_realized_edges) | extra


def _surrogate_extra_measurement(
    *,
    measurement: str,
    jitter: float,
    rng: np.random.Generator,
) -> float:
    if measurement == 'fraction':
        baseline = 0.5
    elif measurement == 'position':
        baseline = 0.0
    else:
        raise ValueError(f'unsupported measurement: {measurement}')
    return float(baseline + rng.normal(loc=0.0, scale=jitter))


def make_active_set_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    candidate_graph: str,
    candidate_parameter: float,
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
    true_row_noise_sigma: float = 0.005,
    extra_row_noise_sigma: float = 0.03,
    extra_row_model: str = 'midpoint_surrogate',
) -> ActiveSetInstance:
    """Create one Experiment E instance.

    The candidate graph is a guaranteed supergraph because the true realized
    pairs are included explicitly. This keeps the experiment focused on pruning
    false positives rather than on recall limited by candidate-generation misses.
    """
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
    true_realized_edges = {
        tuple(sorted((int(i), int(j))))
        for i, j in zip(base.resolved_constraints.i.tolist(), base.resolved_constraints.j.tolist(), strict=True)
    }
    candidate_edges = tuple(
        sorted(
            _candidate_edge_set(
                base.points,
                true_realized_edges,
                candidate_graph=candidate_graph,
                candidate_parameter=candidate_parameter,
            )
        )
    )
    rng = np.random.default_rng(seed ^ 0xE3F15A0D5C3B87A1)

    true_mask: list[bool] = []
    true_target: list[float] = []
    observed_target: list[float] = []
    candidate_raw_constraints: list[tuple[int, int, float]] = []
    for i, j in candidate_edges:
        exact_value = _pair_measurement(
            base.points,
            base.true_weights,
            i,
            j,
            measurement=measurement,
        )
        is_true = (i, j) in true_realized_edges
        if is_true:
            observed_value = float(exact_value + rng.normal(loc=0.0, scale=true_row_noise_sigma))
        else:
            if extra_row_model != 'midpoint_surrogate':
                raise ValueError(f'unsupported extra_row_model: {extra_row_model}')
            observed_value = _surrogate_extra_measurement(
                measurement=measurement,
                jitter=extra_row_noise_sigma,
                rng=rng,
            )
        true_mask.append(is_true)
        true_target.append(float(exact_value))
        observed_target.append(float(observed_value))
        candidate_raw_constraints.append((int(i), int(j), float(observed_value)))

    candidate_constraints = pyvoro2.resolve_pair_bisector_constraints(
        base.points,
        candidate_raw_constraints,
        measurement=measurement,
        domain=base.domain,
        image='nearest',
    )
    true_mask_arr = np.asarray(true_mask, dtype=bool)
    true_pair_count = int(np.sum(true_mask_arr))
    candidate_pair_count = int(len(true_mask_arr))
    extra_pair_count = int(candidate_pair_count - true_pair_count)
    precision = 1.0 if candidate_pair_count == 0 else float(true_pair_count / candidate_pair_count)
    recall = 1.0  # the candidate construction explicitly includes the realized graph
    f1 = 0.0 if (precision + recall) == 0.0 else float(2.0 * precision * recall / (precision + recall))

    return ActiveSetInstance(
        base=base,
        candidate_graph=str(candidate_graph),
        candidate_parameter=float(candidate_parameter),
        extra_row_model=str(extra_row_model),
        candidate_raw_constraints=candidate_raw_constraints,
        candidate_constraints=candidate_constraints,
        candidate_edges=candidate_edges,
        true_realized_edges=tuple(sorted(true_realized_edges)),
        true_realized_mask=true_mask_arr,
        true_target=np.asarray(true_target, dtype=float),
        observed_target=np.asarray(observed_target, dtype=float),
        extra_pair_count=extra_pair_count,
        candidate_pair_count=candidate_pair_count,
        true_pair_count=true_pair_count,
        candidate_pair_precision=precision,
        candidate_pair_recall=recall,
        candidate_pair_f1=f1,
        true_row_noise_sigma=float(true_row_noise_sigma),
        extra_row_noise_sigma=float(extra_row_noise_sigma),
        seed=int(seed),
    )


def mask_metrics(selected_mask: np.ndarray, truth_mask: np.ndarray) -> BinaryMaskMetrics:
    """Return precision/recall/F1 of a selected row set against truth."""
    selected = np.asarray(selected_mask, dtype=bool)
    truth = np.asarray(truth_mask, dtype=bool)
    if selected.shape != truth.shape:
        raise ValueError('selected_mask and truth_mask must have the same shape')
    tp = int(np.sum(selected & truth))
    fp = int(np.sum(selected & ~truth))
    fn = int(np.sum(~selected & truth))
    n_selected = int(np.sum(selected))
    precision = 1.0 if (tp + fp) == 0 else float(tp / (tp + fp))
    recall = 1.0 if (tp + fn) == 0 else float(tp / (tp + fn))
    f1 = 0.0 if (precision + recall) == 0.0 else float(2.0 * precision * recall / (precision + recall))
    return BinaryMaskMetrics(
        n_selected=n_selected,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def rmse_on_mask(predicted: np.ndarray, target: np.ndarray, mask: np.ndarray) -> float:
    """RMSE of predicted values against target on a Boolean mask."""
    pred = np.asarray(predicted, dtype=float)
    tgt = np.asarray(target, dtype=float)
    sel = np.asarray(mask, dtype=bool)
    if pred.shape != tgt.shape or pred.shape != sel.shape:
        raise ValueError('predicted, target, and mask must share the same shape')
    if not np.any(sel):
        return float('nan')
    err = pred[sel] - tgt[sel]
    return float(np.sqrt(np.mean(err * err)))
