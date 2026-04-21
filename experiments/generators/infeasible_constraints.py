"""Generators and feasibility utilities for Experiment D.

Experiment D is about *hard* pairwise restrictions.  It does not benchmark a
soft penalty or a generic optimizer.  Instead, it exercises the theorem-level
statement from the manuscript: pairwise measurement bounds induce linear bounds
on weight differences, and infeasibility is witnessed by a negative cycle.

The synthetic instances below start from exact connected power-diagram data,
extract a short realized-pair cycle, and then build feasible or infeasible hard
restriction systems on that support.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pyvoro2

from experiments.generators.exact_recovery import ExactRecoveryInstance
from experiments.generators.missing_data import make_connected_exact_instance

MeasurementMode = Literal['fraction', 'position']


@dataclass(frozen=True)
class DifferenceConstraintConflictTerm:
    """One inequality term participating in a contradiction witness."""

    constraint_index: int
    site_i: int
    site_j: int
    relation: str
    bound_value: float


@dataclass(frozen=True)
class DifferenceConstraintConflict:
    """Negative-cycle witness for an infeasible difference-bound system."""

    component_nodes: tuple[int, ...]
    cycle_nodes: tuple[int, ...]
    terms: tuple[DifferenceConstraintConflictTerm, ...]
    message: str
    cycle_total: float


@dataclass(frozen=True)
class DifferenceConstraintResult:
    """Result of the Bellman--Ford feasibility check."""

    feasible: bool
    weights: np.ndarray | None
    conflict: DifferenceConstraintConflict | None
    max_violation: float | None
    min_lower_slack: float | None
    min_upper_slack: float | None


@dataclass(frozen=True)
class InfeasibleConstraintInstance:
    """One hard-constraint benchmark instance for Experiment D."""

    base: ExactRecoveryInstance
    support_row_indices_global: np.ndarray
    support_constraints: pyvoro2.PairBisectorConstraints
    scenario: str
    feasible_expected: bool
    cycle_row_indices_global: np.ndarray
    cycle_nodes: tuple[int, ...]
    measurement_lower: np.ndarray
    measurement_upper: np.ndarray
    difference_lower: np.ndarray
    difference_upper: np.ndarray
    perturbed_local_index: int | None
    generation_attempts: int
    note: str


@dataclass(frozen=True)
class SupportDiagnostics:
    """Structural information about the chosen support cycle."""

    n_support_constraints: int
    n_support_nodes: int
    cycle_length: int
    has_outside_fraction_edge: bool
    outside_fraction_edge_count: int
    support_target_min: float
    support_target_max: float


def _measurement_target(constraints: pyvoro2.PairBisectorConstraints) -> np.ndarray:
    if constraints.measurement == 'fraction':
        return np.asarray(constraints.target_fraction, dtype=float)
    if constraints.measurement == 'position':
        return np.asarray(constraints.target_position, dtype=float)
    raise ValueError(f'unsupported measurement: {constraints.measurement}')


def measurement_to_difference_bounds(
    constraints: pyvoro2.PairBisectorConstraints,
    lower: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert measurement-space bounds to weight-difference bounds."""
    lower_arr = np.asarray(lower, dtype=float)
    upper_arr = np.asarray(upper, dtype=float)
    if lower_arr.shape != (constraints.n_constraints,):
        raise ValueError('lower has wrong shape')
    if upper_arr.shape != (constraints.n_constraints,):
        raise ValueError('upper has wrong shape')
    if np.any(upper_arr < lower_arr):
        raise ValueError('measurement bounds require upper >= lower rowwise')

    if constraints.measurement == 'fraction':
        alpha = 1.0 / (2.0 * np.asarray(constraints.distance2, dtype=float))
        beta = np.full(constraints.n_constraints, 0.5, dtype=float)
    elif constraints.measurement == 'position':
        alpha = 1.0 / (2.0 * np.asarray(constraints.distance, dtype=float))
        beta = 0.5 * np.asarray(constraints.distance, dtype=float)
    else:
        raise ValueError(f'unsupported measurement: {constraints.measurement}')

    z_lo = (lower_arr - beta) / alpha
    z_hi = (upper_arr - beta) / alpha
    return np.minimum(z_lo, z_hi), np.maximum(z_lo, z_hi)


def _subset_raw_constraints(
    base: ExactRecoveryInstance,
    row_indices_global: np.ndarray,
) -> list[tuple]:
    input_index = np.asarray(base.resolved_constraints.input_index, dtype=int)
    return [
        base.raw_constraints[int(input_index[idx])]
        for idx in np.asarray(row_indices_global, dtype=int).tolist()
    ]


def _resolve_subset(
    base: ExactRecoveryInstance,
    row_indices_global: np.ndarray,
) -> pyvoro2.PairBisectorConstraints:
    raw_subset = _subset_raw_constraints(base, row_indices_global)
    return pyvoro2.resolve_pair_bisector_constraints(
        base.points,
        raw_subset,
        measurement=base.measurement,
        domain=base.domain,
        image='nearest',
    )


def _graph_edges(constraints: pyvoro2.PairBisectorConstraints) -> list[tuple[int, int]]:
    return [
        (int(i), int(j))
        for i, j in zip(constraints.i.tolist(), constraints.j.tolist(), strict=True)
    ]


def _bfs_path_rows_excluding(
    n_points: int,
    edges: list[tuple[int, int]],
    *,
    source: int,
    target: int,
    forbidden_row: int,
) -> list[int] | None:
    adj: list[list[tuple[int, int]]] = [[] for _ in range(n_points)]
    for row_idx, (u, v) in enumerate(edges):
        if row_idx == forbidden_row:
            continue
        adj[u].append((v, row_idx))
        adj[v].append((u, row_idx))

    prev_node = np.full(n_points, -1, dtype=int)
    prev_row = np.full(n_points, -1, dtype=int)
    queue = [int(source)]
    prev_node[source] = source
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        if u == target:
            break
        for v, row_idx in adj[u]:
            if prev_node[v] != -1:
                continue
            prev_node[v] = u
            prev_row[v] = row_idx
            queue.append(v)
    if prev_node[target] == -1:
        return None

    rows_rev: list[int] = []
    cur = int(target)
    while cur != source:
        rows_rev.append(int(prev_row[cur]))
        cur = int(prev_node[cur])
    rows_rev.reverse()
    return rows_rev


def shortest_cycle_row_indices(
    constraints: pyvoro2.PairBisectorConstraints,
    *,
    required_row_mask: np.ndarray | None = None,
) -> np.ndarray | None:
    """Return row indices of a short simple cycle in the undirected support graph.

    When ``required_row_mask`` is given, the returned cycle must contain at least
    one marked row.
    """
    edges = _graph_edges(constraints)
    n_points = int(constraints.n_points)
    best: list[int] | None = None
    mask = None if required_row_mask is None else np.asarray(required_row_mask, dtype=bool)
    if mask is not None and mask.shape != (len(edges),):
        raise ValueError('required_row_mask has wrong shape')

    row_iter = range(len(edges)) if mask is None else [idx for idx, keep in enumerate(mask.tolist()) if keep]
    for row_idx in row_iter:
        u, v = edges[row_idx]
        path_rows = _bfs_path_rows_excluding(
            n_points,
            edges,
            source=u,
            target=v,
            forbidden_row=row_idx,
        )
        if path_rows is None:
            continue
        cycle_rows = path_rows + [row_idx]
        if best is None or len(cycle_rows) < len(best):
            best = cycle_rows
    if best is None:
        return None
    return np.asarray(best, dtype=int)


def _cycle_node_sequence(
    n_points: int,
    edges: list[tuple[int, int]],
    cycle_rows: np.ndarray,
) -> tuple[int, ...]:
    if cycle_rows.size == 0:
        return tuple()
    cycle_set = {int(idx) for idx in np.asarray(cycle_rows, dtype=int).tolist()}
    cycle_edges = [edges[idx] for idx in cycle_rows.tolist()]

    adj: list[list[int]] = [[] for _ in range(n_points)]
    edge_lookup: dict[tuple[int, int], int] = {}
    for idx, (u, v) in zip(cycle_rows.tolist(), cycle_edges, strict=True):
        adj[u].append(v)
        adj[v].append(u)
        edge_lookup[(u, v)] = idx
        edge_lookup[(v, u)] = idx

    start = min(min(u, v) for u, v in cycle_edges)
    path = [start]
    prev = -1
    cur = start
    while True:
        nbrs = sorted(adj[cur])
        nxt = nbrs[0] if nbrs[0] != prev else (nbrs[1] if len(nbrs) > 1 else -1)
        if nxt < 0:
            break
        path.append(nxt)
        prev, cur = cur, nxt
        if cur == start:
            break
    if len(path) >= 2 and path[-1] == start:
        path.pop()
    if len(path) != len(cycle_set):
        nodes = sorted({u for u, _ in cycle_edges} | {v for _, v in cycle_edges})
        return tuple(int(v) for v in nodes)
    return tuple(int(v) for v in path)


def support_diagnostics(instance: InfeasibleConstraintInstance) -> SupportDiagnostics:
    target = np.asarray(instance.support_constraints.target_fraction, dtype=float)
    unique_nodes = np.unique(
        np.concatenate(
            [
                np.asarray(instance.support_constraints.i, dtype=int),
                np.asarray(instance.support_constraints.j, dtype=int),
            ]
        )
    )
    outside = np.logical_or(target < 0.0, target > 1.0)
    return SupportDiagnostics(
        n_support_constraints=int(instance.support_constraints.n_constraints),
        n_support_nodes=int(unique_nodes.size),
        cycle_length=int(instance.cycle_row_indices_global.size),
        has_outside_fraction_edge=bool(np.any(outside)),
        outside_fraction_edge_count=int(np.sum(outside)),
        support_target_min=float(np.min(target)),
        support_target_max=float(np.max(target)),
    )


def _simple_component_nodes(
    n_points: int,
    i_idx: np.ndarray,
    j_idx: np.ndarray,
    seed_nodes: set[int],
) -> tuple[int, ...]:
    adj: list[list[int]] = [[] for _ in range(n_points)]
    for i, j in zip(i_idx.tolist(), j_idx.tolist(), strict=True):
        adj[i].append(j)
        adj[j].append(i)
    seen = np.zeros(n_points, dtype=bool)
    out: set[int] = set()
    for start in seed_nodes:
        if seen[start]:
            continue
        stack = [int(start)]
        seen[start] = True
        while stack:
            u = stack.pop()
            out.add(u)
            for v in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
    return tuple(sorted(int(v) for v in out))


@dataclass(frozen=True)
class _RelaxEdge:
    source: int
    target: int
    weight: float
    constraint_index: int
    site_i: int
    site_j: int
    relation: Literal['<=', '>=']
    bound_value: float


def solve_difference_bounds(
    n_points: int,
    i_idx: np.ndarray,
    j_idx: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    *,
    tol: float = 1.0e-12,
) -> DifferenceConstraintResult:
    """Bellman--Ford feasibility check for difference constraints.

    The system is
        ``lower[k] <= w_i - w_j <= upper[k]``.
    A feasible vector is returned when one exists.  Otherwise a negative cycle
    is extracted as a compact contradiction witness.
    """
    i_arr = np.asarray(i_idx, dtype=int)
    j_arr = np.asarray(j_idx, dtype=int)
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    if not (i_arr.shape == j_arr.shape == lo.shape == hi.shape):
        raise ValueError('all arrays must have the same shape')
    if np.any(hi < lo):
        raise ValueError('difference bounds require upper >= lower rowwise')

    edges: list[_RelaxEdge] = []
    for row_idx, (i, j, ell, uu) in enumerate(
        zip(i_arr.tolist(), j_arr.tolist(), lo.tolist(), hi.tolist(), strict=True)
    ):
        edges.append(
            _RelaxEdge(
                source=int(j),
                target=int(i),
                weight=float(uu),
                constraint_index=int(row_idx),
                site_i=int(i),
                site_j=int(j),
                relation='<=',
                bound_value=float(uu),
            )
        )
        edges.append(
            _RelaxEdge(
                source=int(i),
                target=int(j),
                weight=float(-ell),
                constraint_index=int(row_idx),
                site_i=int(i),
                site_j=int(j),
                relation='>=',
                bound_value=float(ell),
            )
        )

    dist = np.zeros(int(n_points), dtype=float)
    pred_node = np.full(int(n_points), -1, dtype=int)
    pred_edge = np.full(int(n_points), -1, dtype=int)
    last_updated = -1

    for _ in range(int(n_points)):
        updated = False
        last_updated = -1
        for edge_idx, edge in enumerate(edges):
            cand = float(dist[edge.source] + edge.weight)
            if cand < float(dist[edge.target] - tol):
                dist[edge.target] = cand
                pred_node[edge.target] = edge.source
                pred_edge[edge.target] = edge_idx
                updated = True
                last_updated = edge.target
        if not updated:
            diff = dist[i_arr] - dist[j_arr]
            lower_slack = diff - lo
            upper_slack = hi - diff
            max_violation = float(
                max(
                    np.max(np.maximum(-lower_slack, 0.0), initial=0.0),
                    np.max(np.maximum(-upper_slack, 0.0), initial=0.0),
                )
            )
            return DifferenceConstraintResult(
                feasible=True,
                weights=dist.copy(),
                conflict=None,
                max_violation=max_violation,
                min_lower_slack=float(np.min(lower_slack)) if lower_slack.size else 0.0,
                min_upper_slack=float(np.min(upper_slack)) if upper_slack.size else 0.0,
            )

    if last_updated < 0:
        return DifferenceConstraintResult(
            feasible=True,
            weights=dist.copy(),
            conflict=None,
            max_violation=0.0,
            min_lower_slack=None,
            min_upper_slack=None,
        )

    y = int(last_updated)
    for _ in range(int(n_points)):
        y = int(pred_node[y])
        if y < 0:
            return DifferenceConstraintResult(
                feasible=False,
                weights=None,
                conflict=None,
                max_violation=None,
                min_lower_slack=None,
                min_upper_slack=None,
            )

    cycle_edges_rev: list[_RelaxEdge] = []
    cur = y
    while True:
        edge_index = int(pred_edge[cur])
        if edge_index < 0:
            return DifferenceConstraintResult(
                feasible=False,
                weights=None,
                conflict=None,
                max_violation=None,
                min_lower_slack=None,
                min_upper_slack=None,
            )
        edge = edges[edge_index]
        cycle_edges_rev.append(edge)
        cur = edge.source
        if cur == y:
            break
    cycle_edges = tuple(reversed(cycle_edges_rev))
    cycle_nodes_list: list[int] = []
    if cycle_edges:
        cycle_nodes_list.append(cycle_edges[0].source)
        cycle_nodes_list.extend(edge.target for edge in cycle_edges)
        if len(cycle_nodes_list) >= 2 and cycle_nodes_list[0] == cycle_nodes_list[-1]:
            cycle_nodes_list.pop()
    cycle_total = float(sum(edge.weight for edge in cycle_edges))
    seed_nodes = set(int(v) for v in cycle_nodes_list)
    component_nodes = _simple_component_nodes(int(n_points), i_arr, j_arr, seed_nodes)
    unique_rows = tuple(sorted({edge.constraint_index for edge in cycle_edges}))
    conflict = DifferenceConstraintConflict(
        component_nodes=component_nodes,
        cycle_nodes=tuple(int(v) for v in cycle_nodes_list),
        terms=tuple(
            DifferenceConstraintConflictTerm(
                constraint_index=edge.constraint_index,
                site_i=edge.site_i,
                site_j=edge.site_j,
                relation=edge.relation,
                bound_value=edge.bound_value,
            )
            for edge in cycle_edges
        ),
        message=(
            'inconsistent hard separator restrictions on connected component '
            + '[' + ', '.join(str(v) for v in component_nodes) + ']'
            + '; contradiction cycle uses constraint rows '
            + '[' + ', '.join(str(v) for v in unique_rows) + ']'
        ),
        cycle_total=cycle_total,
    )
    return DifferenceConstraintResult(
        feasible=False,
        weights=None,
        conflict=conflict,
        max_violation=None,
        min_lower_slack=None,
        min_upper_slack=None,
    )


def edge_difference_rmse(
    true_weights: np.ndarray,
    fit_weights: np.ndarray,
    constraints: pyvoro2.PairBisectorConstraints,
) -> float:
    """RMSE of support-edge weight differences against the exact generator."""
    true_arr = np.asarray(true_weights, dtype=float)
    fit_arr = np.asarray(fit_weights, dtype=float)
    diff_true = true_arr[np.asarray(constraints.i, dtype=int)] - true_arr[np.asarray(constraints.j, dtype=int)]
    diff_fit = fit_arr[np.asarray(constraints.i, dtype=int)] - fit_arr[np.asarray(constraints.j, dtype=int)]
    return float(np.sqrt(np.mean((diff_fit - diff_true) ** 2))) if diff_true.size else 0.0


def _build_instance_from_support(
    *,
    base: ExactRecoveryInstance,
    generation_attempts: int,
    support_row_indices_global: np.ndarray,
    cycle_row_indices_global: np.ndarray,
    scenario: str,
    feasible_expected: bool,
    measurement_lower: np.ndarray,
    measurement_upper: np.ndarray,
    perturbed_local_index: int | None,
    note: str,
) -> InfeasibleConstraintInstance:
    support_constraints = _resolve_subset(base, support_row_indices_global)
    diff_lower, diff_upper = measurement_to_difference_bounds(
        support_constraints,
        measurement_lower,
        measurement_upper,
    )
    cycle_nodes = _cycle_node_sequence(
        int(base.resolved_constraints.n_points),
        _graph_edges(base.resolved_constraints),
        np.asarray(cycle_row_indices_global, dtype=int),
    )
    return InfeasibleConstraintInstance(
        base=base,
        support_row_indices_global=np.asarray(support_row_indices_global, dtype=int),
        support_constraints=support_constraints,
        scenario=str(scenario),
        feasible_expected=bool(feasible_expected),
        cycle_row_indices_global=np.asarray(cycle_row_indices_global, dtype=int),
        cycle_nodes=cycle_nodes,
        measurement_lower=np.asarray(measurement_lower, dtype=float),
        measurement_upper=np.asarray(measurement_upper, dtype=float),
        difference_lower=np.asarray(diff_lower, dtype=float),
        difference_upper=np.asarray(diff_upper, dtype=float),
        perturbed_local_index=None if perturbed_local_index is None else int(perturbed_local_index),
        generation_attempts=int(generation_attempts),
        note=str(note),
    )


def make_cyclic_exact_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    measurement: MeasurementMode = 'fraction',
    weight_scale: float = 0.08,
    require_outside_fraction_edge: bool = False,
    max_attempts: int = 80,
) -> tuple[ExactRecoveryInstance, int, np.ndarray]:
    """Generate a connected exact instance and a short realized-pair cycle."""
    for attempt in range(int(max_attempts)):
        trial_seed = int(seed) + 500009 * attempt
        base, _ = make_connected_exact_instance(
            n_sites=n_sites,
            dim=dim,
            seed=trial_seed,
            measurement=measurement,
            weight_scale=weight_scale,
            max_attempts=8,
        )
        required_mask = None
        if require_outside_fraction_edge:
            target_fraction = np.asarray(base.resolved_constraints.target_fraction, dtype=float)
            required_mask = np.logical_or(target_fraction < 0.0, target_fraction > 1.0)
            if not np.any(required_mask):
                continue
        cycle_rows = shortest_cycle_row_indices(base.resolved_constraints, required_row_mask=required_mask)
        if cycle_rows is not None:
            return base, attempt + 1, cycle_rows
    raise RuntimeError(
        'failed to generate a cyclic exact instance '
        f'(dim={dim}, n_sites={n_sites}, require_outside_fraction_edge={require_outside_fraction_edge})'
    )


def make_infeasible_constraint_instance(
    *,
    scenario: str,
    n_sites: int,
    dim: int,
    seed: int,
    measurement: MeasurementMode = 'fraction',
    weight_scale: float = 0.08,
    interval_halfwidth: float = 0.01,
    contradiction_shift: float = 0.06,
    between_points_interval: tuple[float, float] = (0.0, 1.0),
    max_generation_attempts: int = 80,
) -> InfeasibleConstraintInstance:
    """Build one Experiment D scenario from an exact support cycle."""
    if measurement != 'fraction':
        raise ValueError('the current Experiment D generator is defined for fraction-space restrictions')

    require_outside = scenario == 'between_points_violation'
    base, attempts, cycle_rows = make_cyclic_exact_instance(
        n_sites=n_sites,
        dim=dim,
        seed=seed,
        measurement=measurement,
        weight_scale=(max(weight_scale, 0.12) if require_outside else weight_scale),
        require_outside_fraction_edge=require_outside,
        max_attempts=max_generation_attempts,
    )
    support_constraints = _resolve_subset(base, cycle_rows)
    target = _measurement_target(support_constraints)
    pivot = int(np.argmax(np.asarray(support_constraints.distance2, dtype=float)))

    if scenario == 'exact_equalities':
        lower = target.copy()
        upper = target.copy()
        note = 'exact equality restrictions on a short realized-pair cycle'
        feasible = True
        perturbed = None
    elif scenario == 'narrow_intervals':
        band = float(interval_halfwidth)
        lower = target - band
        upper = target + band
        note = 'narrow feasible intervals centered at the exact cycle measurements'
        feasible = True
        perturbed = None
    elif scenario == 'contradictory_equalities':
        lower = target.copy()
        upper = target.copy()
        lower[pivot] += float(contradiction_shift)
        upper[pivot] += float(contradiction_shift)
        note = 'one equality row is shifted, breaking cycle consistency'
        feasible = False
        perturbed = pivot
    elif scenario == 'contradictory_intervals':
        band = float(interval_halfwidth)
        lower = target.copy()
        upper = target.copy()
        lower[pivot] = target[pivot] + float(contradiction_shift) - band
        upper[pivot] = target[pivot] + float(contradiction_shift) + band
        note = 'one interval row is shifted away from the exact cycle value'
        feasible = False
        perturbed = pivot
    elif scenario == 'between_points_violation':
        target_fraction = np.asarray(support_constraints.target_fraction, dtype=float)
        outside_idx = np.flatnonzero(np.logical_or(target_fraction < 0.0, target_fraction > 1.0))
        if outside_idx.size == 0:
            raise RuntimeError('between_points_violation requires a cycle edge with exact fraction outside [0, 1]')
        pivot = int(outside_idx[0])
        lower = target.copy()
        upper = target.copy()
        interval = tuple(float(v) for v in between_points_interval)
        lower[pivot] = interval[0]
        upper[pivot] = interval[1]
        if upper[pivot] < lower[pivot]:
            raise ValueError('between_points_interval must satisfy upper >= lower')
        note = 'one cycle edge is forced into the between-points interval [0, 1] while the exact cycle value lies outside it'
        feasible = False
        perturbed = pivot
    else:
        raise ValueError(f'unsupported scenario: {scenario}')

    return _build_instance_from_support(
        base=base,
        generation_attempts=attempts,
        support_row_indices_global=cycle_rows,
        cycle_row_indices_global=cycle_rows,
        scenario=scenario,
        feasible_expected=feasible,
        measurement_lower=lower,
        measurement_upper=upper,
        perturbed_local_index=perturbed,
        note=note,
    )
