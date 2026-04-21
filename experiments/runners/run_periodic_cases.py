#!/usr/bin/env python3
"""Run Experiment F: periodic wrong-image stress tests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import yaml

if __package__ is None or __package__ == '':
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments._provenance import build_runtime_provenance  # noqa: E402
from experiments.generators.periodic_cases import (  # noqa: E402
    image_choice_accuracy,
    make_corrupted_periodic_observation,
    make_periodic_exact_instance,
    mean_shift_l1_distance,
    measurement_rmse,
    refine_periodic_shifts,
    resolve_periodic_rows,
    realized_shift_rates,
    run_periodic_fit,
    true_pair_difference_rmse,
)


SCENARIO_ORDER = [
    'correct_images',
    'noisy_correct_images',
    'wrong_images_authoritative',
    'nearest_image_inference',
    'realized_shift_refinement',
]


def _case_seed(base_seed: int, *parts: object) -> int:
    payload = '|'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'little') ^ int(base_seed)


def _expand_n_sites(config: dict[str, Any]) -> dict[int, list[int]]:
    raw = config['n_sites_by_dimension']
    return {int(key): [int(v) for v in values] for key, values in raw.items()}


def _smoke_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    cfg['replicates'] = min(int(cfg.get('replicates', 1)), 4)
    cfg['dimensions'] = [2, 3]
    cfg['n_sites_by_dimension'] = {2: [16], 3: [24]}
    cfg['corruption_fractions'] = [0.25]
    cfg['noise_sigma_control'] = float(cfg.get('noise_sigma_control', 0.01))
    cfg['shift_refinement_max_iter'] = min(int(cfg.get('shift_refinement_max_iter', 3)), 3)
    return cfg


def _row_from_result(
    *,
    scenario: str,
    corruption_fraction_requested: float,
    actual_corruption_fraction: float,
    n_corrupted_rows: int,
    measurement_noise_sigma: float,
    instance,
    constraints,
    fit,
    realized,
    runtime_sec: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rates = realized_shift_rates(realized)
    predicted = np.asarray(fit.predicted, dtype=float)
    row = {
        'seed': int(instance.seed),
        'dimension': int(instance.base.dimension),
        'n_sites': int(instance.base.points.shape[0]),
        'scenario': str(scenario),
        'measurement': constraints.measurement,
        'n_constraints': int(len(constraints.target)),
        'corruption_fraction': float(corruption_fraction_requested),
        'actual_corruption_fraction': float(actual_corruption_fraction),
        'n_corrupted_rows': int(n_corrupted_rows),
        'measurement_noise_sigma': float(measurement_noise_sigma),
        'image_choice_accuracy': image_choice_accuracy(constraints, instance.true_constraints),
        'mean_shift_l1_distance': mean_shift_l1_distance(constraints, instance.true_constraints),
        'clean_separator_rmse': measurement_rmse(predicted, instance.clean_target),
        'observed_separator_rmse': measurement_rmse(predicted, np.asarray(constraints.target, dtype=float)),
        'pair_difference_rmse': true_pair_difference_rmse(instance, np.asarray(fit.weights, dtype=float)),
        'status': fit.status,
        'status_detail': getattr(fit, 'status_detail', None),
        'solver': fit.solver,
        'n_iter': int(getattr(fit, 'n_iter', 0)),
        'converged': bool(getattr(fit, 'converged', False)),
        'runtime_sec': float(runtime_sec),
        'unaccounted_pair_count': int(len(realized.unaccounted_pairs)),
        'warnings_fit': ' | '.join(getattr(fit, 'warnings', ())),
        'warnings_realized': ' | '.join(getattr(realized, 'warnings', ())),
    } | rates
    if extra:
        row |= extra
    return row


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['scenario', 'dimension', 'n_sites', 'corruption_fraction']

    def _q(prob: float):
        return lambda s: float(pd.Series(s).quantile(prob))

    agg_map: dict[str, tuple[str, str]] = {
        'runs': ('seed', 'count'),
        'actual_corruption_fraction_mean': ('actual_corruption_fraction', 'mean'),
        'measurement_noise_sigma_mean': ('measurement_noise_sigma', 'mean'),
        'n_constraints_mean': ('n_constraints', 'mean'),
        'n_corrupted_rows_mean': ('n_corrupted_rows', 'mean'),
        'image_choice_accuracy_mean': ('image_choice_accuracy', 'mean'),
        'image_choice_accuracy_q25': ('image_choice_accuracy', _q(0.25)),
        'image_choice_accuracy_q75': ('image_choice_accuracy', _q(0.75)),
        'image_choice_accuracy_min': ('image_choice_accuracy', 'min'),
        'mean_shift_l1_distance_mean': ('mean_shift_l1_distance', 'mean'),
        'clean_separator_rmse_mean': ('clean_separator_rmse', 'mean'),
        'clean_separator_rmse_q25': ('clean_separator_rmse', _q(0.25)),
        'clean_separator_rmse_q75': ('clean_separator_rmse', _q(0.75)),
        'clean_separator_rmse_max': ('clean_separator_rmse', 'max'),
        'observed_separator_rmse_mean': ('observed_separator_rmse', 'mean'),
        'pair_difference_rmse_mean': ('pair_difference_rmse', 'mean'),
        'pair_difference_rmse_q25': ('pair_difference_rmse', _q(0.25)),
        'pair_difference_rmse_q75': ('pair_difference_rmse', _q(0.75)),
        'realized_same_shift_rate_mean': ('realized_same_shift_rate', 'mean'),
        'realized_other_shift_rate_mean': ('realized_other_shift_rate', 'mean'),
        'realized_other_shift_rate_q25': ('realized_other_shift_rate', _q(0.25)),
        'realized_other_shift_rate_q75': ('realized_other_shift_rate', _q(0.75)),
        'realized_any_rate_mean': ('realized_any_rate', 'mean'),
        'unrealized_rate_mean': ('unrealized_rate', 'mean'),
        'unaccounted_pair_count_mean': ('unaccounted_pair_count', 'mean'),
        'status_optimal_rate': ('status', lambda s: float(np.mean(pd.Series(s) == 'optimal'))),
        'converged_rate': ('converged', 'mean'),
        'runtime_sec_mean': ('runtime_sec', 'mean'),
        'runtime_sec_q25': ('runtime_sec', _q(0.25)),
        'runtime_sec_q75': ('runtime_sec', _q(0.75)),
    }
    optional = {
        'shift_refinement_iterations_mean': 'shift_refinement_iterations',
        'shift_refinement_converged_rate': 'shift_refinement_converged',
        'shift_rows_reassigned_total_mean': 'shift_rows_reassigned_total',
        'shift_rows_reassigned_last_mean': 'shift_rows_reassigned_last',
        'unique_realized_rows_last_mean': 'unique_realized_rows_last',
        'ambiguous_realized_rows_last_mean': 'ambiguous_realized_rows_last',
        'unrealized_rows_last_mean': 'unrealized_rows_last',
        'initial_image_choice_accuracy_mean': 'initial_image_choice_accuracy',
        'initial_realized_other_shift_rate_mean': 'initial_realized_other_shift_rate',
        'initial_clean_separator_rmse_mean': 'initial_clean_separator_rmse',
    }
    for outcol, incol in optional.items():
        if incol in df.columns:
            agg_map[outcol] = (incol, 'mean')
    summary = df.groupby(group_cols, dropna=False, observed=True).agg(**agg_map).reset_index()
    summary['scenario'] = pd.Categorical(summary['scenario'], categories=SCENARIO_ORDER, ordered=True)
    return summary.sort_values(['dimension', 'n_sites', 'corruption_fraction', 'scenario']).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/periodic.yaml'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = Path(args.output_dir or config.get('output_dir', 'results/periodic'))
    output_dir.mkdir(parents=True, exist_ok=True)

    measurement = str(config.get('measurement', 'fraction'))
    weight_scale = float(config.get('weight_scale', 0.08))
    fit_solver = str(config.get('fit_solver', 'analytic'))
    shift_refinement_max_iter = int(config.get('shift_refinement_max_iter', 3))
    scenarios = [str(item) for item in config.get('scenarios', SCENARIO_ORDER)]
    rows: list[dict[str, Any]] = []

    for dim in [int(d) for d in config.get('dimensions', [])]:
        for n_sites in _expand_n_sites(config).get(dim, []):
            for rep in range(int(config.get('replicates', 1))):
                base_seed = _case_seed(int(config.get('seed', 0)), 'F', dim, n_sites, rep)
                instance = make_periodic_exact_instance(
                    n_sites=int(n_sites),
                    dim=int(dim),
                    seed=base_seed,
                    measurement=measurement,
                    weight_scale=weight_scale,
                    validate_periodic_planar_shifts=False,
                )
                points = instance.base.points
                domain = instance.base.domain

                if 'correct_images' in scenarios:
                    observation = make_corrupted_periodic_observation(
                        instance,
                        corruption_fraction=0.0,
                        measurement_noise_sigma=0.0,
                        seed=_case_seed(base_seed, 'correct_images'),
                    )
                    constraints = resolve_periodic_rows(
                        points,
                        observation.authoritative_rows,
                        domain=domain,
                        measurement=measurement,
                        image='given_only',
                    )
                    t0 = time.perf_counter()
                    fit, realized = run_periodic_fit(points, constraints, domain=domain, fit_solver=fit_solver)
                    runtime_sec = float(time.perf_counter() - t0)
                    rows.append(
                        _row_from_result(
                            scenario='correct_images',
                            corruption_fraction_requested=0.0,
                            actual_corruption_fraction=0.0,
                            n_corrupted_rows=0,
                            measurement_noise_sigma=0.0,
                            instance=instance,
                            constraints=constraints,
                            fit=fit,
                            realized=realized,
                            runtime_sec=runtime_sec,
                        )
                    )

                if 'noisy_correct_images' in scenarios:
                    sigma = float(config.get('noise_sigma_control', 0.01))
                    observation = make_corrupted_periodic_observation(
                        instance,
                        corruption_fraction=0.0,
                        measurement_noise_sigma=sigma,
                        seed=_case_seed(base_seed, 'noisy_correct_images'),
                    )
                    constraints = resolve_periodic_rows(
                        points,
                        observation.authoritative_rows,
                        domain=domain,
                        measurement=measurement,
                        image='given_only',
                    )
                    t0 = time.perf_counter()
                    fit, realized = run_periodic_fit(points, constraints, domain=domain, fit_solver=fit_solver)
                    runtime_sec = float(time.perf_counter() - t0)
                    rows.append(
                        _row_from_result(
                            scenario='noisy_correct_images',
                            corruption_fraction_requested=0.0,
                            actual_corruption_fraction=0.0,
                            n_corrupted_rows=0,
                            measurement_noise_sigma=sigma,
                            instance=instance,
                            constraints=constraints,
                            fit=fit,
                            realized=realized,
                            runtime_sec=runtime_sec,
                        )
                    )

                for corruption_fraction in [float(v) for v in config.get('corruption_fractions', [])]:
                    observation = make_corrupted_periodic_observation(
                        instance,
                        corruption_fraction=float(corruption_fraction),
                        measurement_noise_sigma=0.0,
                        seed=_case_seed(base_seed, 'corrupt', corruption_fraction),
                    )

                    if 'wrong_images_authoritative' in scenarios:
                        constraints = resolve_periodic_rows(
                            points,
                            observation.authoritative_rows,
                            domain=domain,
                            measurement=measurement,
                            image='given_only',
                        )
                        t0 = time.perf_counter()
                        fit, realized = run_periodic_fit(points, constraints, domain=domain, fit_solver=fit_solver)
                        runtime_sec = float(time.perf_counter() - t0)
                        rows.append(
                            _row_from_result(
                                scenario='wrong_images_authoritative',
                                corruption_fraction_requested=float(corruption_fraction),
                                actual_corruption_fraction=observation.corruption_fraction_actual,
                                n_corrupted_rows=int(np.sum(observation.corrupted_row_mask)),
                                measurement_noise_sigma=0.0,
                                instance=instance,
                                constraints=constraints,
                                fit=fit,
                                realized=realized,
                                runtime_sec=runtime_sec,
                            )
                        )

                    nearest_constraints = None
                    nearest_fit = None
                    nearest_realized = None
                    nearest_runtime = None
                    if 'nearest_image_inference' in scenarios or 'realized_shift_refinement' in scenarios:
                        nearest_constraints = resolve_periodic_rows(
                            points,
                            observation.stripped_rows,
                            domain=domain,
                            measurement=measurement,
                            image='nearest',
                        )
                        t0 = time.perf_counter()
                        nearest_fit, nearest_realized = run_periodic_fit(
                            points,
                            nearest_constraints,
                            domain=domain,
                            fit_solver=fit_solver,
                        )
                        nearest_runtime = float(time.perf_counter() - t0)

                    if 'nearest_image_inference' in scenarios and nearest_constraints is not None:
                        rows.append(
                            _row_from_result(
                                scenario='nearest_image_inference',
                                corruption_fraction_requested=float(corruption_fraction),
                                actual_corruption_fraction=observation.corruption_fraction_actual,
                                n_corrupted_rows=int(np.sum(observation.corrupted_row_mask)),
                                measurement_noise_sigma=0.0,
                                instance=instance,
                                constraints=nearest_constraints,
                                fit=nearest_fit,
                                realized=nearest_realized,
                                runtime_sec=float(nearest_runtime),
                            )
                        )

                    if 'realized_shift_refinement' in scenarios and nearest_constraints is not None:
                        t0 = time.perf_counter()
                        refined = refine_periodic_shifts(
                            points,
                            nearest_constraints,
                            domain=domain,
                            fit_solver=fit_solver,
                            max_iter=shift_refinement_max_iter,
                        )
                        runtime_sec = float((nearest_runtime or 0.0) + (time.perf_counter() - t0))
                        initial_rates = realized_shift_rates(nearest_realized)
                        rows.append(
                            _row_from_result(
                                scenario='realized_shift_refinement',
                                corruption_fraction_requested=float(corruption_fraction),
                                actual_corruption_fraction=observation.corruption_fraction_actual,
                                n_corrupted_rows=int(np.sum(observation.corrupted_row_mask)),
                                measurement_noise_sigma=0.0,
                                instance=instance,
                                constraints=refined.constraints,
                                fit=refined.fit,
                                realized=refined.realized,
                                runtime_sec=runtime_sec,
                                extra={
                                    'shift_refinement_iterations': int(refined.n_iterations),
                                    'shift_refinement_converged': bool(refined.converged),
                                    'shift_rows_reassigned_total': int(refined.total_rows_reassigned),
                                    'shift_rows_reassigned_last': int(refined.last_rows_reassigned),
                                    'unique_realized_rows_last': int(refined.last_unique_realized),
                                    'ambiguous_realized_rows_last': int(refined.last_ambiguous_realized),
                                    'unrealized_rows_last': int(refined.last_unrealized_rows),
                                    'initial_image_choice_accuracy': image_choice_accuracy(nearest_constraints, instance.true_constraints),
                                    'initial_realized_other_shift_rate': float(initial_rates['realized_other_shift_rate']),
                                    'initial_clean_separator_rmse': measurement_rmse(
                                        np.asarray(nearest_fit.predicted, dtype=float),
                                        instance.clean_target,
                                    ),
                                },
                            )
                        )

    runs = pd.DataFrame.from_records(rows)
    runs['scenario'] = pd.Categorical(runs['scenario'], categories=SCENARIO_ORDER, ordered=True)
    runs = runs.sort_values(['dimension', 'n_sites', 'corruption_fraction', 'scenario', 'seed']).reset_index(drop=True)
    summary = _summary_frame(runs)

    runs_path = output_dir / 'runs.csv'
    summary_path = output_dir / 'summary.csv'
    meta_path = output_dir / 'metadata.json'
    runs.to_csv(runs_path, index=False)
    summary.to_csv(summary_path, index=False)
    with meta_path.open('w', encoding='utf-8') as fh:
        json.dump(
            {
                'config': config,
                'preset': 'smoke' if args.smoke else 'archived',
                'n_runs': len(rows),
                'output_files': {
                    'runs': runs_path.name,
                    'summary': summary_path.name,
                },
                'scenario_order': SCENARIO_ORDER,
                'provenance': build_runtime_provenance(),
            },
            fh,
            indent=2,
        )

    print(summary.to_string(index=False))
    print(f'\nWrote: {runs_path}')
    print(f'Wrote: {summary_path}')
    print(f'Wrote: {meta_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
