"""Synthetic periodic image-stress cases for Experiment F.

Experiment F isolates a phenomenon that does not occur in the non-periodic
setting: the same site pair can be realized through different lattice images,
and trusting the wrong image metadata can produce a distinctive failure mode.

The benchmark is built from exact periodic power-diagram instances. From the
true realized-pair rows we derive three kinds of periodic input:

- clean controls with the correct explicit shifts;
- wrong-image rows where a prescribed fraction of shifts is replaced by an
  incorrect nearby lattice offset; and
- shift-stripped rows, where the pair identities and measurements are kept but
  the image is re-inferred or refined on the paper side.

The intent is to measure not merely whether the residual increases, but whether
wrong-image corruption leaves a recognizable signature in realized-pair
analysis, especially via ``realized_other_shift`` diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
from typing import Any

import numpy as np
import pyvoro2

from experiments.generators.exact_recovery import (
    ExactRecoveryInstance,
    make_exact_recovery_instance,
    pair_difference_rmse,
)


@dataclass(frozen=True)
class PeriodicExactInstance:
    """One exact periodic instance for Experiment F."""

    base: ExactRecoveryInstance
    true_constraints: pyvoro2.PairBisectorConstraints
    true_raw_constraints: tuple[tuple[int, int, float, tuple[int, ...]], ...]
    clean_target: np.ndarray
    seed: int


@dataclass(frozen=True)
class CorruptedPeriodicObservation:
    """Observed periodic rows before constraint resolution."""

    base: PeriodicExactInstance
    corruption_fraction_requested: float
    corruption_fraction_actual: float
    measurement_noise_sigma: float
    corrupted_row_mask: np.ndarray
    observed_values: np.ndarray
    authoritative_rows: tuple[tuple[int, int, float, tuple[int, ...]], ...]
    stripped_rows: tuple[tuple[int, int, float], ...]
    seed: int


@dataclass(frozen=True)
class ShiftRefinementResult:
    """Result of the realized-shift refinement loop."""

    constraints: pyvoro2.PairBisectorConstraints
    fit: Any
    realized: Any
    n_iterations: int
    converged: bool
    total_rows_reassigned: int
    last_rows_reassigned: int
    last_unique_realized: int
    last_ambiguous_realized: int
    last_unrealized_rows: int


_NEARBY_SHIFT_CACHE: dict[int, tuple[tuple[int, ...], ...]] = {}


def _nearby_shift_candidates(dim: int) -> tuple[tuple[int, ...], ...]:
    cached = _NEARBY_SHIFT_CACHE.get(int(dim))
    if cached is not None:
        return cached
    values = tuple(tuple(int(v) for v in row) for row in itertools.product((-1, 0, 1), repeat=int(dim)))
    _NEARBY_SHIFT_CACHE[int(dim)] = values
    return values


def make_periodic_exact_instance(
    *,
    n_sites: int,
    dim: int,
    seed: int,
    measurement: str = 'fraction',
    weight_scale: float = 0.08,
    validate_periodic_planar_shifts: bool = False,
) -> PeriodicExactInstance:
    """Create one exact periodic base instance for Experiment F."""
    if dim not in {2, 3}:
        raise ValueError(f'unsupported dimension: {dim}')
    base = make_exact_recovery_instance(
        n_sites=n_sites,
        dim=dim,
        periodic=True,
        seed=seed,
        graph_variant='full_realized',
        measurement=measurement,
        weight_scale=weight_scale,
        validate_periodic_planar_shifts=validate_periodic_planar_shifts,
    )
    if not base.periodic:
        raise ValueError('Experiment F requires a periodic exact-recovery instance')
    true_constraints = base.resolved_constraints
    if true_constraints.shifts.shape[1] != dim:
        raise ValueError('resolved periodic shifts do not match the requested dimension')
    true_raw = tuple(
        (int(i), int(j), float(value), tuple(int(v) for v in shift))
        for i, j, value, shift in base.raw_constraints
    )
    return PeriodicExactInstance(
        base=base,
        true_constraints=true_constraints,
        true_raw_constraints=true_raw,
        clean_target=np.asarray(true_constraints.target, dtype=float).copy(),
        seed=int(seed),
    )


def _choose_corrupted_rows(n_rows: int, fraction: float, rng: np.random.Generator) -> np.ndarray:
    fraction = float(fraction)
    if fraction <= 0.0:
        return np.zeros(int(n_rows), dtype=bool)
    n_bad = int(round(fraction * n_rows))
    if n_bad <= 0 and n_rows > 0:
        n_bad = 1
    n_bad = min(max(n_bad, 0), int(n_rows))
    mask = np.zeros(int(n_rows), dtype=bool)
    if n_bad:
        mask[np.asarray(rng.choice(int(n_rows), size=n_bad, replace=False), dtype=int)] = True
    return mask


def _corrupt_shift(true_shift: tuple[int, ...], *, dim: int, rng: np.random.Generator) -> tuple[int, ...]:
    candidates = [shift for shift in _nearby_shift_candidates(dim) if shift != tuple(int(v) for v in true_shift)]
    if not candidates:
        raise RuntimeError('failed to construct alternative periodic shifts')
    return candidates[int(rng.integers(len(candidates)))]


def make_corrupted_periodic_observation(
    base: PeriodicExactInstance,
    *,
    corruption_fraction: float,
    measurement_noise_sigma: float,
    seed: int,
) -> CorruptedPeriodicObservation:
    """Corrupt a fraction of explicit periodic shifts and optionally add noise."""
    rng = np.random.default_rng(seed)
    true_rows = base.true_raw_constraints
    dim = int(base.base.dimension)
    mask = _choose_corrupted_rows(len(true_rows), float(corruption_fraction), rng)
    observed_values = np.asarray(base.clean_target, dtype=float).copy()
    sigma = float(measurement_noise_sigma)
    if sigma > 0.0:
        observed_values = observed_values + rng.normal(loc=0.0, scale=sigma, size=observed_values.shape)

    authoritative_rows: list[tuple[int, int, float, tuple[int, ...]]] = []
    stripped_rows: list[tuple[int, int, float]] = []
    for idx, (i, j, _, shift) in enumerate(true_rows):
        used_shift = _corrupt_shift(shift, dim=dim, rng=rng) if bool(mask[idx]) else shift
        value = float(observed_values[idx])
        authoritative_rows.append((int(i), int(j), value, tuple(int(v) for v in used_shift)))
        stripped_rows.append((int(i), int(j), value))

    return CorruptedPeriodicObservation(
        base=base,
        corruption_fraction_requested=float(corruption_fraction),
        corruption_fraction_actual=float(np.mean(mask)) if len(mask) else 0.0,
        measurement_noise_sigma=sigma,
        corrupted_row_mask=mask,
        observed_values=np.asarray(observed_values, dtype=float),
        authoritative_rows=tuple(authoritative_rows),
        stripped_rows=tuple(stripped_rows),
        seed=int(seed),
    )


def resolve_periodic_rows(
    points: np.ndarray,
    rows: tuple[tuple[int, int, float], ...] | tuple[tuple[int, int, float, tuple[int, ...]], ...],
    *,
    domain: Any,
    measurement: str,
    image: str,
) -> pyvoro2.PairBisectorConstraints:
    """Resolve periodic pair rows into a ``PairBisectorConstraints`` object."""
    return pyvoro2.resolve_pair_bisector_constraints(
        points,
        rows,
        measurement=measurement,
        domain=domain,
        image=image,
    )


def run_periodic_fit(
    points: np.ndarray,
    constraints: pyvoro2.PairBisectorConstraints,
    *,
    domain: Any,
    fit_solver: str = 'analytic',
):
    """Solve the periodic inverse fit and match realized pairs."""
    fit = pyvoro2.fit_power_weights(
        points,
        constraints,
        measurement=constraints.measurement,
        domain=domain,
        solver=str(fit_solver),
        connectivity_check='diagnose',
    )
    realized = pyvoro2.match_realized_pairs(
        points,
        domain=domain,
        radii=np.asarray(fit.radii, dtype=float),
        constraints=constraints,
        unaccounted_pair_check='diagnose',
        tessellation_check='diagnose',
    )
    return fit, realized


def refine_periodic_shifts(
    points: np.ndarray,
    initial_constraints: pyvoro2.PairBisectorConstraints,
    *,
    domain: Any,
    fit_solver: str = 'analytic',
    max_iter: int = 3,
) -> ShiftRefinementResult:
    """Refine periodic images using realized-shift diagnostics.

    Starting from an initial periodic constraint set, repeatedly:

    1. fit power weights,
    2. query which shifts actually realize each row under the fitted diagram,
    3. replace a row's current shift when the realized image is unique.

    The loop is intentionally lightweight; its purpose is to test whether
    periodic image mismatches can be repaired from the fit's own realized-pair
    diagnostics.
    """
    constraints = initial_constraints
    total_rows_reassigned = 0
    last_rows_reassigned = 0
    last_unique = 0
    last_ambiguous = 0
    last_unrealized = 0

    for iteration in range(1, int(max_iter) + 1):
        fit, realized = run_periodic_fit(points, constraints, domain=domain, fit_solver=fit_solver)
        new_rows: list[tuple[int, int, float, tuple[int, ...]]] = []
        changed = 0
        unique_realized = 0
        ambiguous_realized = 0
        unrealized_rows = 0

        for idx in range(len(constraints.target)):
            cur_shift = tuple(int(v) for v in constraints.shifts[idx])
            realized_shifts = tuple(tuple(int(v) for v in shift) for shift in realized.realized_shifts[idx])
            if len(realized_shifts) == 1:
                new_shift = realized_shifts[0]
                unique_realized += 1
            else:
                new_shift = cur_shift
                if len(realized_shifts) == 0:
                    unrealized_rows += 1
                else:
                    ambiguous_realized += 1
            if new_shift != cur_shift:
                changed += 1
            new_rows.append(
                (
                    int(constraints.i[idx]),
                    int(constraints.j[idx]),
                    float(constraints.target[idx]),
                    tuple(int(v) for v in new_shift),
                )
            )

        total_rows_reassigned += changed
        last_rows_reassigned = int(changed)
        last_unique = int(unique_realized)
        last_ambiguous = int(ambiguous_realized)
        last_unrealized = int(unrealized_rows)

        if changed == 0:
            return ShiftRefinementResult(
                constraints=constraints,
                fit=fit,
                realized=realized,
                n_iterations=int(iteration),
                converged=True,
                total_rows_reassigned=int(total_rows_reassigned),
                last_rows_reassigned=int(last_rows_reassigned),
                last_unique_realized=int(last_unique),
                last_ambiguous_realized=int(last_ambiguous),
                last_unrealized_rows=int(last_unrealized),
            )

        constraints = pyvoro2.resolve_pair_bisector_constraints(
            points,
            tuple(new_rows),
            measurement=constraints.measurement,
            domain=domain,
            image='given_only',
        )

    final_fit, final_realized = run_periodic_fit(points, constraints, domain=domain, fit_solver=fit_solver)
    return ShiftRefinementResult(
        constraints=constraints,
        fit=final_fit,
        realized=final_realized,
        n_iterations=int(max_iter),
        converged=False,
        total_rows_reassigned=int(total_rows_reassigned),
        last_rows_reassigned=int(last_rows_reassigned),
        last_unique_realized=int(last_unique),
        last_ambiguous_realized=int(last_ambiguous),
        last_unrealized_rows=int(last_unrealized),
    )


def image_choice_accuracy(
    constraints: pyvoro2.PairBisectorConstraints,
    true_constraints: pyvoro2.PairBisectorConstraints,
) -> float:
    """Fraction of rows whose resolved lattice image matches the exact one."""
    if constraints.shifts.shape != true_constraints.shifts.shape:
        raise ValueError('constraint arrays must have the same periodic-shift shape')
    if len(true_constraints.target) == 0:
        return 1.0
    matches = np.all(np.asarray(constraints.shifts) == np.asarray(true_constraints.shifts), axis=1)
    return float(np.mean(matches))


def mean_shift_l1_distance(
    constraints: pyvoro2.PairBisectorConstraints,
    true_constraints: pyvoro2.PairBisectorConstraints,
) -> float:
    """Mean lattice L1 distance between resolved and exact periodic shifts."""
    if constraints.shifts.shape != true_constraints.shifts.shape:
        raise ValueError('constraint arrays must have the same periodic-shift shape')
    delta = np.abs(np.asarray(constraints.shifts, dtype=int) - np.asarray(true_constraints.shifts, dtype=int))
    return float(np.mean(np.sum(delta, axis=1))) if len(delta) else 0.0


def measurement_rmse(predicted: np.ndarray, reference: np.ndarray) -> float:
    """RMSE between predicted and reference separator measurements."""
    pred = np.asarray(predicted, dtype=float)
    ref = np.asarray(reference, dtype=float)
    if pred.shape != ref.shape:
        raise ValueError('predicted and reference measurements must have the same shape')
    if pred.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((pred - ref) ** 2)))


def realized_shift_rates(realized) -> dict[str, float]:
    """Return the main periodic realization rates from diagnostics."""
    realized_same = np.asarray(realized.realized_same_shift, dtype=bool)
    realized_other = np.asarray(realized.realized_other_shift, dtype=bool)
    realized_any = np.asarray(realized.realized, dtype=bool)
    return {
        'realized_same_shift_rate': float(np.mean(realized_same)) if realized_same.size else 0.0,
        'realized_other_shift_rate': float(np.mean(realized_other)) if realized_other.size else 0.0,
        'realized_any_rate': float(np.mean(realized_any)) if realized_any.size else 0.0,
        'unrealized_rate': 1.0 - (float(np.mean(realized_any)) if realized_any.size else 1.0),
    }


def true_pair_difference_rmse(instance: PeriodicExactInstance, fit_weights: np.ndarray) -> float:
    """Gauge-invariant edge-difference RMSE on the exact periodic rows."""
    return pair_difference_rmse(
        np.asarray(instance.base.true_weights, dtype=float),
        np.asarray(fit_weights, dtype=float),
        instance.true_constraints,
    )
