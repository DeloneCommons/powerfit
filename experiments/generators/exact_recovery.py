"""Synthetic generators for exact-recovery benchmarks.

This module owns only paper-side logic. Core tessellation and inverse fitting stay
in :mod:`pyvoro2`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import math

import numpy as np
import pyvoro2
import pyvoro2.planar as pv2


@dataclass(frozen=True)
class ExactRecoveryInstance:
    """One exact-recovery benchmark instance."""

    points: np.ndarray
    true_weights: np.ndarray
    radii: np.ndarray
    domain: Any
    raw_constraints: list[tuple]
    resolved_constraints: pyvoro2.PairBisectorConstraints
    measurement: str
    dimension: int
    periodic: bool
    graph_variant: str
    seed: int
    periodic_planar_shift_validation: bool


def make_domain(dim: int, periodic: bool):
    if dim == 2:
        bounds = ((0.0, 1.0), (0.0, 1.0))
        return pv2.RectangularCell(bounds, periodic=(True, True)) if periodic else pv2.Box(bounds)
    if dim == 3:
        bounds = ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))
        return (
            pyvoro2.OrthorhombicCell(bounds, periodic=(True, True, True))
            if periodic
            else pyvoro2.Box(bounds)
        )
    raise ValueError(f"unsupported dimension: {dim}")


def _nearest_neighbor_d2(points: np.ndarray, periodic: bool) -> np.ndarray:
    delta = points[:, None, :] - points[None, :, :]
    if periodic:
        delta = delta - np.round(delta)
    d2 = np.sum(delta * delta, axis=2)
    np.fill_diagonal(d2, np.inf)
    return np.min(d2, axis=1)


def sample_points(n_sites: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    """Sample random sites in the unit box/cell.

    Uniform sampling is sufficient here because pyvoro2 already guards against
    fatal near-duplicate inputs in the core code path. The paper-side benchmark
    only needs generic position.
    """
    return rng.random((n_sites, dim), dtype=float)


def sample_power_weights(
    points: np.ndarray,
    *,
    periodic: bool,
    rng: np.random.Generator,
    weight_scale: float = 0.08,
    weight_floor_ratio: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a moderate power perturbation around a Voronoi baseline.

    The scale is expressed relative to the median nearest-neighbour squared
    distance so that exact-recovery instances remain generic across site counts
    and dimensions while avoiding extreme empty-cell regimes.
    """
    nn2 = _nearest_neighbor_d2(points, periodic=periodic)
    sigma = float(weight_scale * np.median(nn2))
    sigma = max(sigma, 1.0e-6)
    relative = rng.normal(loc=0.0, scale=sigma, size=len(points))
    shift = -float(np.min(relative)) + float(weight_floor_ratio * sigma)
    weights = relative + shift
    radii = np.sqrt(weights)
    return weights, radii


def _domain_shift_vector(domain: Any, shift: Iterable[int]) -> np.ndarray:
    shift_arr = np.asarray(tuple(int(v) for v in shift), dtype=float)
    if hasattr(domain, 'vectors'):
        return shift_arr @ np.asarray(domain.vectors, dtype=float)
    bounds = np.asarray(domain.bounds, dtype=float)
    lengths = bounds[:, 1] - bounds[:, 0]
    return shift_arr * lengths


def _canonical_periodic_edge(i: int, j: int, shift: tuple[int, ...]) -> tuple[int, int, tuple[int, ...]]:
    shift = tuple(int(v) for v in shift)
    cur = (int(i), int(j), shift)
    rev = (int(j), int(i), tuple(-v for v in shift))
    return min(cur, rev)


def _raw_realized_pairs_from_cells(
    points: np.ndarray,
    weights: np.ndarray,
    domain: Any,
    *,
    dim: int,
    periodic: bool,
    measurement: str,
    validate_periodic_planar_shifts: bool,
) -> list[tuple]:
    if dim == 2:
        compute_kwargs: dict[str, Any] = {'return_edges': True}
        if periodic:
            compute_kwargs.update(
                return_edge_shifts=True,
                validate_edge_shifts=validate_periodic_planar_shifts,
            )
        cells = pv2.compute(points, domain=domain, mode='power', radii=np.sqrt(weights), **compute_kwargs)
        item_key = 'edges'
        shift_key = 'adjacent_shift'
    else:
        compute_kwargs = {'return_faces': True}
        if periodic:
            compute_kwargs.update(return_face_shifts=True)
        cells = pyvoro2.compute(points, domain=domain, mode='power', radii=np.sqrt(weights), **compute_kwargs)
        item_key = 'faces'
        shift_key = 'adjacent_shift'

    seen: set[tuple[int, int, tuple[int, ...]]] = set()
    raw_constraints: list[tuple] = []
    zero_shift = (0,) * dim

    for cell in cells:
        i = int(cell['id'])
        for item in cell[item_key]:
            j = int(item['adjacent_cell'])
            if j < 0:
                continue
            shift = tuple(item.get(shift_key, zero_shift)) if periodic else zero_shift
            key = _canonical_periodic_edge(i, j, shift)
            cur = (i, j, shift)
            if cur != key or key in seen:
                continue
            seen.add(key)

            delta = points[j] + _domain_shift_vector(domain, shift) - points[i]
            d2 = float(delta @ delta)
            if d2 <= 0.0:
                raise ValueError('encountered non-positive connector length')
            fraction = 0.5 + float((weights[i] - weights[j]) / (2.0 * d2))
            if measurement == 'fraction':
                value = fraction
            elif measurement == 'position':
                value = math.sqrt(d2) * fraction
            else:
                raise ValueError(f'unsupported measurement: {measurement}')
            raw_constraints.append((i, j, value, shift) if periodic else (i, j, value))
    return raw_constraints


def _build_site_graph_edges(constraints: pyvoro2.PairBisectorConstraints) -> list[tuple[int, int]]:
    return [(int(i), int(j)) for i, j in zip(constraints.i.tolist(), constraints.j.tolist(), strict=True)]


def _spanning_tree_parent(n_points: int, edges: list[tuple[int, int]]) -> tuple[list[int], list[int], list[tuple[int, int]]]:
    adj: list[list[int]] = [[] for _ in range(n_points)]
    for i, j in edges:
        if i == j:
            continue
        adj[i].append(j)
        adj[j].append(i)
    parent = [-1] * n_points
    order: list[int] = []
    tree_edges: list[tuple[int, int]] = []
    stack = [0]
    parent[0] = 0
    while stack:
        u = stack.pop()
        order.append(u)
        for v in adj[u]:
            if parent[v] != -1:
                continue
            parent[v] = u
            tree_edges.append((u, v))
            stack.append(v)
    if len(order) != n_points:
        raise ValueError('site graph is disconnected; expected a connected realized graph')
    return parent, order, tree_edges


def make_two_component_subgraph(
    constraints: pyvoro2.PairBisectorConstraints,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return a mask that splits the site graph into two connected components.

    A random tree edge in a spanning tree is removed. The induced partition is
    then used to keep only within-component constraints.
    """
    n_points = constraints.n_points
    site_edges = _build_site_graph_edges(constraints)
    _, _, tree_edges = _spanning_tree_parent(n_points, site_edges)
    if not tree_edges:
        raise ValueError('cannot form a two-component split from a single-vertex graph')
    cut_u, cut_v = tree_edges[int(rng.integers(len(tree_edges)))]

    # Build the spanning tree adjacency and remove the chosen edge.
    tree_adj: list[list[int]] = [[] for _ in range(n_points)]
    for u, v in tree_edges:
        if {u, v} == {cut_u, cut_v}:
            continue
        tree_adj[u].append(v)
        tree_adj[v].append(u)

    side = np.full(n_points, -1, dtype=int)
    stack = [cut_u]
    side[cut_u] = 0
    while stack:
        u = stack.pop()
        for v in tree_adj[u]:
            if side[v] != -1:
                continue
            side[v] = 0
            stack.append(v)
    side[side == -1] = 1

    keep = np.array([side[i] == side[j] for i, j in zip(constraints.i, constraints.j, strict=True)], dtype=bool)
    if not np.any(~keep):
        raise RuntimeError('failed to split constraints into two components')
    return keep


def _subset_raw_constraints(raw_constraints: list[tuple], keep_mask: np.ndarray) -> list[tuple]:
    return [row for row, keep in zip(raw_constraints, keep_mask.tolist(), strict=True) if keep]


def make_exact_recovery_instance(
    *,
    n_sites: int,
    dim: int,
    periodic: bool,
    seed: int,
    graph_variant: str = 'full_realized',
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
    validate_periodic_planar_shifts: bool = False,
) -> ExactRecoveryInstance:
    rng = np.random.default_rng(seed)
    points = sample_points(n_sites, dim, rng)
    true_weights, radii = sample_power_weights(points, periodic=periodic, rng=rng, weight_scale=weight_scale)
    domain = make_domain(dim, periodic)
    raw_constraints = _raw_realized_pairs_from_cells(
        points,
        true_weights,
        domain,
        dim=dim,
        periodic=periodic,
        measurement=measurement,
        validate_periodic_planar_shifts=validate_periodic_planar_shifts,
    )
    resolve_kwargs: dict[str, Any] = {
        'measurement': measurement,
        'domain': domain,
        'image': 'given_only' if periodic else 'nearest',
    }
    resolved = pyvoro2.resolve_pair_bisector_constraints(points, raw_constraints, **resolve_kwargs)

    if graph_variant == 'two_component_subgraph':
        keep = make_two_component_subgraph(resolved, rng)
        raw_constraints = _subset_raw_constraints(raw_constraints, keep)
        resolved = pyvoro2.resolve_pair_bisector_constraints(points, raw_constraints, **resolve_kwargs)
    elif graph_variant != 'full_realized':
        raise ValueError(f'unsupported graph variant: {graph_variant}')

    return ExactRecoveryInstance(
        points=points,
        true_weights=true_weights,
        radii=radii,
        domain=domain,
        raw_constraints=raw_constraints,
        resolved_constraints=resolved,
        measurement=measurement,
        dimension=dim,
        periodic=periodic,
        graph_variant=graph_variant,
        seed=seed,
        periodic_planar_shift_validation=validate_periodic_planar_shifts,
    )


def component_labels(n_points: int, edges: list[tuple[int, int]]) -> np.ndarray:
    parent = list(range(n_points))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j in edges:
        union(int(i), int(j))
    roots = {find(i): idx for idx, i in enumerate(sorted({find(k) for k in range(n_points)}))}
    return np.array([roots[find(i)] for i in range(n_points)], dtype=int)


def componentwise_aligned_rmse(true_weights: np.ndarray, fit_weights: np.ndarray, labels: np.ndarray) -> float:
    aligned = np.array(fit_weights, dtype=float).copy()
    for comp in np.unique(labels):
        mask = labels == comp
        shift = float(np.mean(aligned[mask] - true_weights[mask]))
        aligned[mask] -= shift
    return float(np.sqrt(np.mean((aligned - true_weights) ** 2)))


def pair_difference_rmse(true_weights: np.ndarray, fit_weights: np.ndarray, constraints: pyvoro2.PairBisectorConstraints) -> float:
    diff_true = true_weights[constraints.i] - true_weights[constraints.j]
    diff_fit = fit_weights[constraints.i] - fit_weights[constraints.j]
    return float(np.sqrt(np.mean((diff_fit - diff_true) ** 2)))
