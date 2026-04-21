#!/usr/bin/env python3
"""Run Experiment B: noise and contamination response with squared/Huber fits."""
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

import pyvoro2

if __package__ is None or __package__ == '':
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments._provenance import build_runtime_provenance  # noqa: E402
from experiments.generators.noise_robustness import (  # noqa: E402
    NoiseDescriptor,
    algebraic_residual_metrics,
    make_noise_robustness_instance,
    measurement_recovery_metrics,
    noisy_out_of_segment_rate,
    weight_recovery_metrics,
)


def _case_seed(base_seed: int, *parts: object) -> int:
    payload = '|'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'little') ^ int(base_seed)


def _expand_n_sites(config: dict[str, Any]) -> dict[int, list[int]]:
    raw = config['n_sites_by_dimension']
    return {int(key): [int(v) for v in values] for key, values in raw.items()}


def _expand_noise_conditions(config: dict[str, Any]) -> list[NoiseDescriptor]:
    models = config.get('noise_models', {})
    descriptors: list[NoiseDescriptor] = []
    for sigma in models.get('gaussian', {}).get('sigmas', []):
        descriptors.append(NoiseDescriptor(family='gaussian', sigma=float(sigma)))
    for sigma in models.get('laplace', {}).get('sigmas', []):
        descriptors.append(NoiseDescriptor(family='laplace', sigma=float(sigma)))

    outlier_cfg = models.get('outlier', {})
    background_sigma = float(outlier_cfg.get('background_sigma', 0.0))
    fractions = outlier_cfg.get('fractions', None)
    if fractions is None:
        fractions = [outlier_cfg.get('fraction', 0.05)]
    amplitudes = outlier_cfg.get('amplitudes', [])
    for fraction in fractions:
        for amplitude in amplitudes:
            descriptors.append(
                NoiseDescriptor(
                    family='outlier',
                    sigma=background_sigma,
                    outlier_fraction=float(fraction),
                    outlier_amplitude=float(amplitude),
                )
            )
    if not descriptors:
        raise ValueError('no noise conditions configured')
    return descriptors


def _build_model(method_cfg: dict[str, Any]):
    mismatch_name = str(method_cfg.get('mismatch', 'squared')).lower()
    if mismatch_name == 'squared':
        mismatch = pyvoro2.SquaredLoss()
    elif mismatch_name == 'huber':
        delta = float(method_cfg.get('huber_delta', method_cfg.get('delta', 0.03)))
        mismatch = pyvoro2.HuberLoss(delta=delta)
    else:
        raise ValueError(f'unsupported mismatch for Experiment B: {mismatch_name}')

    feasible = None
    interval = method_cfg.get('hard_interval', None)
    if interval is not None:
        lower, upper = interval
        feasible = pyvoro2.Interval(float(lower), float(upper))

    penalties: list[Any] = []
    if method_cfg.get('soft_interval_penalty') is not None:
        lower, upper, strength = method_cfg['soft_interval_penalty']
        penalties.append(pyvoro2.SoftIntervalPenalty(float(lower), float(upper), float(strength)))

    regularization = pyvoro2.L2Regularization(strength=float(method_cfg.get('l2_strength', 0.0)))
    if (
        mismatch_name == 'squared'
        and feasible is None
        and not penalties
        and regularization.strength == 0.0
    ):
        return None
    return pyvoro2.FitModel(
        mismatch=mismatch,
        feasible=feasible,
        penalties=tuple(penalties),
        regularization=regularization,
    )


def _method_backend(method_cfg: dict[str, Any]) -> str:
    return str(method_cfg.get('backend', 'pyvoro2'))


def _solver_name(method_cfg: dict[str, Any]) -> str:
    return str(method_cfg.get('solver', 'auto'))


def _run_method(
    method_cfg: dict[str, Any],
    *,
    points: np.ndarray,
    constraints: pyvoro2.PairBisectorConstraints,
    domain: Any,
    measurement: str,
):
    backend = _method_backend(method_cfg)
    if backend != 'pyvoro2':
        raise ValueError(f'unsupported method backend: {backend}')
    fit = pyvoro2.fit_power_weights(
        points,
        constraints,
        domain=domain,
        measurement=measurement,
        model=_build_model(method_cfg),
        solver=_solver_name(method_cfg),
        connectivity_check='diagnose',
        max_iter=int(method_cfg.get('max_iter', 5000)),
        tol_abs=float(method_cfg.get('tol_abs', 1.0e-6)),
        tol_rel=float(method_cfg.get('tol_rel', 1.0e-5)),
        rho=float(method_cfg.get('rho', 1.0)),
    )
    return fit


def _smoke_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    cfg['replicates'] = min(int(cfg.get('replicates', 1)), 2)
    cfg['dimensions'] = [2, 3]
    cfg['n_sites_by_dimension'] = {2: [16], 3: [24]}
    cfg['noise_models'] = {
        'gaussian': {'sigmas': [0.005, 0.02]},
        'laplace': {'sigmas': [0.005, 0.02]},
        'outlier': {
            'background_sigma': float(cfg.get('smoke_outlier_background_sigma', 0.005)),
            'fractions': [0.05, 0.10],
            'amplitudes': [0.05],
        },
    }
    return cfg


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['dimension', 'n_sites', 'noise_family', 'noise_level', 'outlier_fraction', 'method']

    def _q(prob: float):
        return lambda s: float(pd.Series(s).quantile(prob))

    agg_map: dict[str, tuple[str, str | Any]] = {
        'runs': ('seed', 'count'),
        'sigma': ('sigma', 'first'),
        'outlier_amplitude': ('outlier_amplitude', 'max'),
        'n_constraints_mean': ('n_constraints', 'mean'),
        'clean_separator_rmse_mean': ('clean_separator_rmse', 'mean'),
        'clean_separator_rmse_q25': ('clean_separator_rmse', _q(0.25)),
        'clean_separator_rmse_q75': ('clean_separator_rmse', _q(0.75)),
        'clean_separator_rmse_max': ('clean_separator_rmse', 'max'),
        'clean_separator_mae_mean': ('clean_separator_mae', 'mean'),
        'noisy_separator_rmse_mean': ('noisy_separator_rmse', 'mean'),
        'edge_difference_rmse_mean': ('edge_difference_rmse', 'mean'),
        'edge_difference_rmse_q25': ('edge_difference_rmse', _q(0.25)),
        'edge_difference_rmse_q75': ('edge_difference_rmse', _q(0.75)),
        'centered_weight_rmse_mean': ('centered_weight_rmse', 'mean'),
        'algebraic_inconsistency_mean': ('algebraic_inconsistency', 'mean'),
        'algebraic_residual_rmse_mean': ('algebraic_residual_rmse', 'mean'),
        'algebraic_residual_rmse_q25': ('algebraic_residual_rmse', _q(0.25)),
        'algebraic_residual_rmse_q75': ('algebraic_residual_rmse', _q(0.75)),
        'realized_any_recall_mean': ('realized_any_recall', 'mean'),
        'realized_any_recall_q25': ('realized_any_recall', _q(0.25)),
        'realized_any_recall_q75': ('realized_any_recall', _q(0.75)),
        'status_optimal_rate': ('status', lambda s: float(np.mean(pd.Series(s) == 'optimal'))),
        'converged_rate': ('converged', 'mean'),
        'runtime_sec_mean': ('runtime_sec', 'mean'),
        'runtime_sec_q25': ('runtime_sec', _q(0.25)),
        'runtime_sec_q75': ('runtime_sec', _q(0.75)),
    }
    optional = {
        'edge_weighted_rmse_mean': 'edge_weighted_rmse',
        'objective_total_mean': 'objective_total',
        'objective_mismatch_mean': 'objective_mismatch',
        'objective_penalties_mean': 'objective_penalties',
        'objective_regularization_mean': 'objective_regularization',
        'hard_max_violation_mean': 'hard_max_violation',
    }
    for outcol, incol in optional.items():
        if incol in df.columns:
            agg_map[outcol] = (incol, 'mean')
    if 'hard_constraints_satisfied' in df.columns:
        agg_map['hard_constraints_satisfied_mean'] = ('hard_constraints_satisfied', 'mean')
    summary = df.groupby(group_cols, dropna=False).agg(**agg_map).reset_index()
    family_order = {'gaussian': 0, 'laplace': 1, 'outlier': 2}
    method_order = {'squared': 0, 'huber': 1}
    return (
        summary.assign(
            _family_order=summary['noise_family'].map(family_order).fillna(99),
            _method_order=summary['method'].map(method_order).fillna(99),
        )
        .sort_values(['dimension', 'n_sites', '_family_order', 'outlier_fraction', 'noise_level', '_method_order'])
        .drop(columns=['_family_order', '_method_order'])
        .reset_index(drop=True)
    )


def _algebraic_metrics_from_fit(fit, constraints: pyvoro2.PairBisectorConstraints) -> tuple[float, float, float]:
    diag = getattr(fit, 'edge_diagnostics', None)
    if diag is not None:
        weighted_l2 = float(diag.weighted_l2) if diag.weighted_l2 is not None else float('nan')
        rmse = float(diag.rmse) if diag.rmse is not None else float('nan')
        weighted_rmse = float(diag.weighted_rmse) if diag.weighted_rmse is not None else float('nan')
        return weighted_l2, rmse, weighted_rmse
    fallback = algebraic_residual_metrics(constraints, np.asarray(fit.weights, dtype=float))
    return float(fallback.weighted_l2), float(fallback.unweighted_rmse), float(fallback.weighted_rmse)


def _objective_metrics_from_fit(fit) -> tuple[float, float, float, float, object, float]:
    parts = getattr(fit, 'objective_breakdown', None)
    if parts is None:
        return float('nan'), float('nan'), float('nan'), float('nan'), None, float('nan')
    return (
        float(parts.total),
        float(parts.mismatch),
        float(parts.penalties_total),
        float(parts.regularization),
        bool(parts.hard_constraints_satisfied),
        float(parts.hard_max_violation),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/noise_robustness.yaml'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = Path(args.output_dir or config.get('output_dir', 'results/noise_robustness'))
    output_dir.mkdir(parents=True, exist_ok=True)

    measurement = str(config.get('measurement', 'fraction'))
    weight_scale = float(config.get('weight_scale', 0.08))
    rows: list[dict[str, Any]] = []

    for dim in [int(d) for d in config.get('dimensions', [])]:
        for n_sites in _expand_n_sites(config).get(dim, []):
            for descriptor in _expand_noise_conditions(config):
                for rep in range(int(config.get('replicates', 1))):
                    seed = _case_seed(int(config.get('seed', 0)), 'B', dim, n_sites, descriptor.label, rep)
                    instance = make_noise_robustness_instance(
                        n_sites=int(n_sites),
                        dim=int(dim),
                        seed=seed,
                        descriptor=descriptor,
                        measurement=measurement,
                        weight_scale=weight_scale,
                    )
                    for method_cfg in config.get('methods', []):
                        t0 = time.perf_counter()
                        fit = _run_method(
                            method_cfg,
                            points=instance.base.points,
                            constraints=instance.noisy_resolved_constraints,
                            domain=instance.base.domain,
                            measurement=instance.base.measurement,
                        )
                        runtime_sec = float(time.perf_counter() - t0)
                        predicted = np.asarray(fit.predicted, dtype=float)
                        measurement_metrics = measurement_recovery_metrics(
                            instance.clean_target,
                            instance.noisy_target,
                            predicted,
                        )
                        weight_metrics = weight_recovery_metrics(
                            instance.base.true_weights,
                            np.asarray(fit.weights, dtype=float),
                            instance.noisy_resolved_constraints,
                        )
                        realized = pyvoro2.match_realized_pairs(
                            instance.base.points,
                            domain=instance.base.domain,
                            radii=fit.radii,
                            constraints=instance.base.resolved_constraints,
                        )
                        algebraic_weighted_l2, algebraic_rmse, edge_weighted_rmse = _algebraic_metrics_from_fit(
                            fit,
                            instance.noisy_resolved_constraints,
                        )
                        objective_total, objective_mismatch, objective_penalties, objective_regularization, hard_satisfied, hard_max_violation = _objective_metrics_from_fit(fit)
                        realized_any = float(np.mean(realized.realized))
                        realized_same = float(np.mean(realized.realized_same_shift))

                        rows.append(
                            {
                                'seed': seed,
                                'dimension': dim,
                                'n_sites': int(n_sites),
                                'noise_family': descriptor.family,
                                'noise_level': descriptor.level,
                                'sigma': descriptor.sigma,
                                'outlier_fraction': descriptor.outlier_fraction,
                                'outlier_amplitude': descriptor.outlier_amplitude,
                                'method': str(method_cfg.get('name', 'squared')),
                                'method_backend': _method_backend(method_cfg),
                                'measurement': instance.base.measurement,
                                'n_constraints': int(instance.noisy_resolved_constraints.n_constraints),
                                'n_outliers': int(np.sum(instance.outlier_mask)),
                                'noisy_out_of_segment_rate': noisy_out_of_segment_rate(instance.noisy_target),
                                'status': fit.status,
                                'status_detail': getattr(fit, 'status_detail', None),
                                'solver': fit.solver,
                                'converged': bool(fit.converged),
                                'n_iter': int(fit.n_iter),
                                'clean_separator_rmse': measurement_metrics.clean_rmse,
                                'clean_separator_mae': measurement_metrics.clean_mae,
                                'noisy_separator_rmse': measurement_metrics.noisy_rmse,
                                'noisy_separator_mae': measurement_metrics.noisy_mae,
                                'edge_difference_rmse': weight_metrics.edge_difference_rmse,
                                'centered_weight_rmse': weight_metrics.centered_weight_rmse,
                                'algebraic_inconsistency': algebraic_weighted_l2,
                                'algebraic_residual_rmse': algebraic_rmse,
                                'edge_weighted_rmse': edge_weighted_rmse,
                                'objective_total': objective_total,
                                'objective_mismatch': objective_mismatch,
                                'objective_penalties': objective_penalties,
                                'objective_regularization': objective_regularization,
                                'hard_constraints_satisfied': hard_satisfied,
                                'hard_max_violation': hard_max_violation,
                                'realized_any_recall': realized_any,
                                'realized_same_shift_recall': realized_same,
                                'runtime_sec': runtime_sec,
                                'fit_rms_residual': float(fit.rms_residual),
                                'fit_max_residual': float(fit.max_residual),
                                'warnings_fit': ' | '.join(fit.warnings),
                                'warnings_realized': ' | '.join(realized.warnings),
                            }
                        )

    runs = pd.DataFrame.from_records(rows)
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
