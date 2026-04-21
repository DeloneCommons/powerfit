"""Row-local connector-visibility diagnostics for fixed-site power diagrams.

These helpers implement the analytic objects used in the manuscript's
connector-visibility theorem package:

- the connector--bisector parameter ``t_ij``;
- competitor slacks ``g_ijk`` at the connector--bisector point;
- the visibility margin ``sigma_ij``;
- the unclipped clearance ``c_ij`` inside the pair bisector;
- the box-clipping margin ``b_ij^B`` for axis-aligned computation boxes.

The functions are deliberately independent of ``pyvoro2`` tessellation objects so
that the paper-side scripts can expose theorem-aligned diagnostics without
modifying the frozen library release.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class CompetitorSlack:
    """Analytic slack of one competitor at the connector--bisector point."""

    competitor: int
    u_ijk: float
    e_norm: float
    slack: float


@dataclass(frozen=True)
class LocalSupportDiagnostics:
    """Analytic row-local diagnostics for one candidate pair."""

    atom_i: int
    atom_j: int
    t_connector: float
    sigma: float
    unclipped_clearance: float
    box_clearance: float
    clipped_clearance: float
    analytic_visible_unclipped: bool
    analytic_visible_clipped: bool
    analytic_margin_safe: bool
    competitor_count: int


ArrayLike = np.ndarray | Iterable[float]


def _as_points(points: ArrayLike) -> np.ndarray:
    arr = np.asarray(points, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f'points must have shape (n_sites, dimension); got {arr.shape!r}')
    return arr



def _as_weights(weights: ArrayLike, n_sites: int) -> np.ndarray:
    arr = np.asarray(weights, dtype=float)
    if arr.ndim != 1 or arr.shape[0] != n_sites:
        raise ValueError(f'weights must have shape ({n_sites},); got {arr.shape!r}')
    return arr



def _pair_geometry(points: np.ndarray, i: int, j: int) -> tuple[np.ndarray, float]:
    delta = np.asarray(points[j] - points[i], dtype=float)
    dd = float(np.dot(delta, delta))
    if dd <= 0.0:
        raise ValueError(f'degenerate pair ({i}, {j}): coincident sites are not supported')
    return delta, dd



def connector_fraction(points: ArrayLike, weights: ArrayLike, i: int, j: int) -> float:
    """Return the connector--bisector fraction t_ij(w)."""

    pts = _as_points(points)
    w = _as_weights(weights, len(pts))
    _delta, dd = _pair_geometry(pts, i, j)
    return float(0.5 + (float(w[i]) - float(w[j])) / (2.0 * dd))



def connector_point(points: ArrayLike, weights: ArrayLike, i: int, j: int) -> np.ndarray:
    """Return the unique connector--bisector point x_ij(w)."""

    pts = _as_points(points)
    t = connector_fraction(pts, weights, i, j)
    return np.asarray(pts[i] + t * (pts[j] - pts[i]), dtype=float)



def competitor_slacks(
    points: ArrayLike,
    weights: ArrayLike,
    i: int,
    j: int,
    *,
    competitors: Iterable[int] | None = None,
) -> list[CompetitorSlack]:
    """Return the analytic competitor slacks g_ijk(w) for all requested k."""

    pts = _as_points(points)
    w = _as_weights(weights, len(pts))
    delta, dd = _pair_geometry(pts, i, j)
    if competitors is None:
        competitors = (k for k in range(len(pts)) if k not in {i, j})
    rows: list[CompetitorSlack] = []
    for k in competitors:
        if k in {i, j}:
            continue
        rel = np.asarray(pts[k] - pts[i], dtype=float)
        u = float(np.dot(rel, delta) / dd)
        e = np.asarray(rel - u * delta, dtype=float)
        e_norm = float(np.linalg.norm(e))
        slack = float(e_norm * e_norm + dd * u * (u - 1.0) + (1.0 - u) * w[i] + u * w[j] - w[k])
        rows.append(CompetitorSlack(competitor=int(k), u_ijk=u, e_norm=e_norm, slack=slack))
    return rows



def visibility_margin(
    points: ArrayLike,
    weights: ArrayLike,
    i: int,
    j: int,
    *,
    competitors: Iterable[int] | None = None,
) -> float:
    """Return sigma_ij(w) = min_k g_ijk(w)."""

    rows = competitor_slacks(points, weights, i, j, competitors=competitors)
    if not rows:
        return float('inf')
    return float(min(row.slack for row in rows))



def unclipped_clearance(
    points: ArrayLike,
    weights: ArrayLike,
    i: int,
    j: int,
    *,
    competitors: Iterable[int] | None = None,
    tol: float = 1.0e-12,
) -> float:
    """Return the analytic clearance inside the unclipped pair bisector.

    The clearance is only meaningful for analytically visible pairs. When the
    pair is not visible the function returns ``nan``. If no off-axis competitor
    exists, the face is unbounded inside the bisector and the clearance is
    reported as ``inf``.
    """

    rows = competitor_slacks(points, weights, i, j, competitors=competitors)
    if not rows:
        return float('inf')
    sigma = min(row.slack for row in rows)
    if not sigma > 0.0:
        return float('nan')
    distances = [row.slack / (2.0 * row.e_norm) for row in rows if row.e_norm > tol]
    if not distances:
        return float('inf')
    return float(min(distances))



def box_clearance(
    points: ArrayLike,
    weights: ArrayLike,
    i: int,
    j: int,
    *,
    bounds: ArrayLike,
    tol: float = 1.0e-12,
) -> float:
    """Return the signed in-plane distance from x_ij(w) to the clipped box boundary.

    The computation box is assumed axis aligned with ``bounds[axis] = (lower,
    upper)``. Positive values mean that the connector--bisector point lies in
    the relative interior of ``H_ij ∩ B``; zero means tangency; negative values
    mean that the point is outside the clipped pair-bisector polygon.
    """

    pts = _as_points(points)
    _w = _as_weights(weights, len(pts))
    x = connector_point(pts, weights, i, j)
    delta, dd = _pair_geometry(pts, i, j)
    normal = delta / math.sqrt(dd)
    bounds_arr = np.asarray(bounds, dtype=float)
    if bounds_arr.shape != (pts.shape[1], 2):
        raise ValueError(f'bounds must have shape ({pts.shape[1]}, 2); got {bounds_arr.shape!r}')

    signed_distances: list[float] = []
    for axis in range(pts.shape[1]):
        lower = float(bounds_arr[axis, 0])
        upper = float(bounds_arr[axis, 1])
        coord = float(x[axis])
        proj_norm_sq = max(0.0, 1.0 - float(normal[axis]) ** 2)
        if proj_norm_sq <= tol:
            # The bisector is parallel to this coordinate direction, so this axis
            # contributes no in-plane boundary unless the bisector misses the box.
            if coord < lower - tol or coord > upper + tol:
                return float('-inf')
            continue
        signed_gap = min(coord - lower, upper - coord)
        signed_distances.append(float(signed_gap / math.sqrt(proj_norm_sq)))

    if not signed_distances:
        # This can only happen in one-dimensional edge cases; treat the clipped
        # section as unbounded inside the bisector.
        return float('inf')
    return float(min(signed_distances))



def analyze_pair_local_support(
    points: ArrayLike,
    weights: ArrayLike,
    i: int,
    j: int,
    *,
    bounds: ArrayLike | None = None,
    competitors: Iterable[int] | None = None,
    tol: float = 1.0e-12,
) -> LocalSupportDiagnostics:
    """Return theorem-aligned local diagnostics for one pair."""

    rows = competitor_slacks(points, weights, i, j, competitors=competitors)
    sigma = float(min((row.slack for row in rows), default=float('inf')))
    visible_unclipped = bool(sigma > tol)
    clear_unclipped = unclipped_clearance(points, weights, i, j, competitors=competitors, tol=tol)

    if bounds is None:
        clear_box = float('inf')
        visible_clipped = visible_unclipped
        clear_clipped = clear_unclipped
        margin_safe = True
    else:
        clear_box = box_clearance(points, weights, i, j, bounds=bounds, tol=tol)
        visible_clipped = bool(visible_unclipped and clear_box > tol)
        if visible_clipped:
            clear_clipped = float(min(clear_unclipped, clear_box))
        else:
            clear_clipped = float('nan')
        margin_safe = bool(visible_clipped and math.isfinite(clear_box) and math.isfinite(clear_unclipped) and clear_box - clear_unclipped > tol)

    return LocalSupportDiagnostics(
        atom_i=int(i),
        atom_j=int(j),
        t_connector=connector_fraction(points, weights, i, j),
        sigma=sigma,
        unclipped_clearance=float(clear_unclipped),
        box_clearance=float(clear_box),
        clipped_clearance=float(clear_clipped),
        analytic_visible_unclipped=visible_unclipped,
        analytic_visible_clipped=visible_clipped,
        analytic_margin_safe=margin_safe,
        competitor_count=len(rows),
    )
