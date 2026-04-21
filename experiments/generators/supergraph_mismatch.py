"""Synthetic generators for Experiment H: supergraph mismatch.

Experiment H combines the two departures separated in Experiments E and G:
- the candidate row set is an overcomplete supergraph rather than an oracle support;
- the target separator rows are generated from a structured non-power law.

The underlying realized support is still known for evaluation, but not for fitting.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyvoro2

from experiments.generators.active_set import _candidate_edge_set, _pair_measurement
from experiments.generators.exact_recovery import ExactRecoveryInstance, make_exact_recovery_instance
from experiments.generators.model_mismatch import (
    _local_context_scores,
    _sample_type_labels,
    observed_targets,
)


@dataclass(frozen=True)
class SupergraphMismatchInstance:
    """One combined support-uncertainty + model-mismatch instance."""

    base: ExactRecoveryInstance
    candidate_graph: str
    candidate_parameter: float
    law_family: str
    eta: float
    candidate_raw_constraints: list[tuple[int, int, float]]
    candidate_constraints: pyvoro2.PairBisectorConstraints
    observed_constraints: pyvoro2.PairBisectorConstraints
    candidate_edges: tuple[tuple[int, int], ...]
    true_realized_edges: tuple[tuple[int, int], ...]
    true_realized_mask: np.ndarray
    exact_target: np.ndarray
    observed_target: np.ndarray
    type_labels: np.ndarray
    local_context: np.ndarray
    clip_fraction: float
    extra_pair_count: int
    candidate_pair_count: int
    true_pair_count: int
    candidate_pair_precision: float
    candidate_pair_recall: float
    candidate_pair_f1: float
    seed: int


def make_supergraph_mismatch_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    candidate_graph: str,
    candidate_parameter: float,
    law_family: str,
    eta: float,
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
    n_types: int = 3,
    k_neighbors: int = 4,
    clip_interval: tuple[float, float] = (0.05, 0.95),
) -> SupergraphMismatchInstance:
    """Create one Experiment H instance."""
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

    candidate_raw_constraints: list[tuple[int, int, float]] = []
    true_mask: list[bool] = []
    exact_target: list[float] = []
    for i, j in candidate_edges:
        exact_value = _pair_measurement(
            base.points,
            base.true_weights,
            i,
            j,
            measurement=measurement,
        )
        candidate_raw_constraints.append((int(i), int(j), float(exact_value)))
        true_mask.append((int(i), int(j)) in true_realized_edges)
        exact_target.append(float(exact_value))

    candidate_constraints = pyvoro2.resolve_pair_bisector_constraints(
        base.points,
        candidate_raw_constraints,
        measurement=measurement,
        domain=base.domain,
        image='nearest',
    )

    rng = np.random.default_rng(seed ^ 0x1E2A95BD73F084CD)
    type_labels = _sample_type_labels(int(base.points.shape[0]), int(n_types), rng)
    local_context = _local_context_scores(base.points, k_neighbors=int(k_neighbors))
    observed_target, clip_fraction = observed_targets(
        candidate_constraints,
        law_family=law_family,
        eta=float(eta),
        type_labels=type_labels,
        local_context=local_context,
        clip_interval=clip_interval,
    )
    observed_rows = [
        (int(i), int(j), float(y))
        for i, j, y in zip(candidate_constraints.i.tolist(), candidate_constraints.j.tolist(), observed_target.tolist(), strict=True)
    ]
    observed_constraints = pyvoro2.resolve_pair_bisector_constraints(
        base.points,
        observed_rows,
        measurement=measurement,
        domain=base.domain,
        image='nearest',
    )

    true_mask_arr = np.asarray(true_mask, dtype=bool)
    true_pair_count = int(np.sum(true_mask_arr))
    candidate_pair_count = int(len(true_mask_arr))
    extra_pair_count = int(candidate_pair_count - true_pair_count)
    precision = 1.0 if candidate_pair_count == 0 else float(true_pair_count / candidate_pair_count)
    recall = 1.0
    f1 = 0.0 if (precision + recall) == 0.0 else float(2.0 * precision * recall / (precision + recall))

    return SupergraphMismatchInstance(
        base=base,
        candidate_graph=str(candidate_graph),
        candidate_parameter=float(candidate_parameter),
        law_family=str(law_family),
        eta=float(eta),
        candidate_raw_constraints=candidate_raw_constraints,
        candidate_constraints=candidate_constraints,
        observed_constraints=observed_constraints,
        candidate_edges=candidate_edges,
        true_realized_edges=tuple(sorted(true_realized_edges)),
        true_realized_mask=true_mask_arr,
        exact_target=np.asarray(exact_target, dtype=float),
        observed_target=np.asarray(observed_target, dtype=float),
        type_labels=np.asarray(type_labels, dtype=int),
        local_context=np.asarray(local_context, dtype=float),
        clip_fraction=float(clip_fraction),
        extra_pair_count=extra_pair_count,
        candidate_pair_count=candidate_pair_count,
        true_pair_count=true_pair_count,
        candidate_pair_precision=precision,
        candidate_pair_recall=recall,
        candidate_pair_f1=f1,
        seed=int(seed),
    )
