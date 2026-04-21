#!/usr/bin/env python3
"""Run Experiment H: supergraph uncertainty under structured mismatch."""
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
from experiments.generators.active_set import mask_metrics, rmse_on_mask  # noqa: E402
from pyvoro2.powerfit.active import ActiveSetOptions  # noqa: E402
from experiments.generators.noise_robustness import algebraic_residual_metrics  # noqa: E402
from experiments.generators.supergraph_mismatch import make_supergraph_mismatch_instance  # noqa: E402


METHOD_ORDER = ['one_shot_fit', 'self_consistent_refinement']


def _case_seed(base_seed: int, *parts: object) -> int:
    payload = '|'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'little') ^ int(base_seed)


def _expand_n_sites(config: dict[str, Any]) -> dict[int, list[int]]:
    return {int(k): [int(v) for v in values] for k, values in config['n_sites_by_dimension'].items()}


def _smoke_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    cfg['replicates'] = 2
    cfg['n_sites_by_dimension'] = {2: [16], 3: [24]}
    cfg['etas'] = [0.00, 0.20]
    return cfg


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['method', 'candidate_graph', 'dimension', 'n_sites', 'law_family', 'eta']
    return (
        df.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            candidate_parameter_mean=('candidate_parameter', 'mean'),
            clip_fraction_mean=('clip_fraction', 'mean'),
            true_pair_count_mean=('true_pair_count', 'mean'),
            candidate_pair_count_mean=('candidate_pair_count', 'mean'),
            extra_pair_count_mean=('extra_pair_count', 'mean'),
            candidate_pair_precision_mean=('candidate_pair_precision', 'mean'),
            candidate_pair_f1_mean=('candidate_pair_f1', 'mean'),
            selected_pair_count_mean=('selected_pair_count', 'mean'),
            selected_pair_precision_mean=('selected_pair_precision', 'mean'),
            selected_pair_recall_mean=('selected_pair_recall', 'mean'),
            selected_pair_f1_mean=('selected_pair_f1', 'mean'),
            true_realized_separator_rmse_mean=('true_realized_separator_rmse', 'mean'),
            all_candidate_separator_rmse_mean=('all_candidate_separator_rmse', 'mean'),
            projection_residual_rmse_mean=('projection_residual_rmse', 'mean'),
            false_positive_count_mean=('false_positive_count', 'mean'),
            false_negative_count_mean=('false_negative_count', 'mean'),
            realized_selected_fraction_mean=('realized_selected_fraction', 'mean'),
            convergence_rate=('converged', 'mean'),
            cycle_detected_rate=('cycle_detected', 'mean'),
            outer_iterations_mean=('outer_iterations', 'mean'),
            marginal_count_mean=('marginal_count', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/supergraph_mismatch.yaml'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = Path(args.output_dir or config.get('output_dir', 'results/supergraph_mismatch'))
    output_dir.mkdir(parents=True, exist_ok=True)

    measurement = str(config.get('measurement', 'fraction'))
    weight_scale = float(config.get('weight_scale', 0.08))
    fit_solver = str(config.get('fit_solver', 'analytic'))
    law_family = str(config.get('law_family', 'type_cycle'))
    clip_interval = tuple(float(v) for v in config.get('clip_interval', [0.05, 0.95]))

    active_cfg = dict(config.get('active_set_options', {}))
    active_options = ActiveSetOptions(
        add_after=int(active_cfg.get('add_after', 1)),
        drop_after=int(active_cfg.get('drop_after', 2)),
        relax=float(active_cfg.get('relax', 1.0)),
        max_iter=int(active_cfg.get('max_iter', 25)),
        cycle_window=int(active_cfg.get('cycle_window', 8)),
        weight_step_tol=float(active_cfg.get('weight_step_tol', 1.0e-8)),
    )
    rows: list[dict[str, Any]] = []

    for dim in [int(v) for v in config.get('dimensions', [])]:
        for n_sites in _expand_n_sites(config).get(dim, []):
            for candidate_spec in config.get('candidate_graphs', []):
                candidate_graph = str(candidate_spec['name'])
                parameter_by_dimension = candidate_spec['parameter_by_dimension']
                candidate_parameter = float(parameter_by_dimension[str(dim)] if str(dim) in parameter_by_dimension else parameter_by_dimension[dim])
                for eta in [float(v) for v in config.get('etas', [])]:
                    for rep in range(int(config.get('replicates', 1))):
                        seed = _case_seed(config.get('seed', 0), 'H', dim, n_sites, candidate_graph, candidate_parameter, law_family, eta, rep)
                        instance = make_supergraph_mismatch_instance(
                            n_sites=int(n_sites),
                            dim=int(dim),
                            seed=int(seed),
                            candidate_graph=candidate_graph,
                            candidate_parameter=float(candidate_parameter),
                            law_family=law_family,
                            eta=float(eta),
                            measurement=measurement,
                            weight_scale=weight_scale,
                            n_types=int(config.get('n_types', 3)),
                            k_neighbors=int(config.get('local_context_k', 4)),
                            clip_interval=clip_interval,
                        )

                        base_row = {
                            'seed': seed,
                            'dimension': int(dim),
                            'n_sites': int(n_sites),
                            'measurement': instance.observed_constraints.measurement,
                            'candidate_graph': candidate_graph,
                            'candidate_parameter': float(candidate_parameter),
                            'law_family': instance.law_family,
                            'eta': float(instance.eta),
                            'clip_fraction': float(instance.clip_fraction),
                            'true_pair_count': int(instance.true_pair_count),
                            'candidate_pair_count': int(instance.candidate_pair_count),
                            'extra_pair_count': int(instance.extra_pair_count),
                            'candidate_pair_precision': float(instance.candidate_pair_precision),
                            'candidate_pair_recall': float(instance.candidate_pair_recall),
                            'candidate_pair_f1': float(instance.candidate_pair_f1),
                        }

                        t0 = time.perf_counter()
                        one_shot_fit = pyvoro2.fit_power_weights(
                            instance.base.points,
                            instance.observed_constraints,
                            measurement=instance.observed_constraints.measurement,
                            domain=instance.base.domain,
                            solver=fit_solver,
                            connectivity_check='diagnose',
                        )
                        one_shot_realized = pyvoro2.match_realized_pairs(
                            instance.base.points,
                            domain=instance.base.domain,
                            radii=np.asarray(one_shot_fit.radii, dtype=float),
                            constraints=instance.observed_constraints,
                            unaccounted_pair_check='diagnose',
                            tessellation_check='diagnose',
                        )
                        one_runtime = float(time.perf_counter() - t0)
                        one_selected = np.asarray(one_shot_realized.realized_same_shift, dtype=bool)
                        one_metrics = mask_metrics(one_selected, instance.true_realized_mask)
                        one_predicted = np.asarray(one_shot_fit.predicted, dtype=float)
                        one_algebraic = algebraic_residual_metrics(
                            instance.observed_constraints,
                            np.asarray(one_shot_fit.weights, dtype=float),
                        )
                        rows.append(
                            base_row
                            | {
                                'method': 'one_shot_fit',
                                'selected_pair_count': int(one_metrics.n_selected),
                                'true_positive_count': int(one_metrics.true_positives),
                                'false_positive_count': int(one_metrics.false_positives),
                                'false_negative_count': int(one_metrics.false_negatives),
                                'selected_pair_precision': float(one_metrics.precision),
                                'selected_pair_recall': float(one_metrics.recall),
                                'selected_pair_f1': float(one_metrics.f1),
                                'realized_selected_fraction': float(np.mean(one_selected)),
                                'true_realized_separator_rmse': rmse_on_mask(one_predicted, instance.observed_target, instance.true_realized_mask),
                                'all_candidate_separator_rmse': rmse_on_mask(
                                    one_predicted,
                                    instance.observed_target,
                                    np.ones_like(instance.true_realized_mask, dtype=bool),
                                ),
                                'projection_residual_rmse': float(one_algebraic.unweighted_rmse),
                                'status': one_shot_fit.status,
                                'status_detail': getattr(one_shot_fit, 'status_detail', None),
                                'solver': one_shot_fit.solver,
                                'converged': bool(getattr(one_shot_fit, 'converged', one_shot_fit.status == 'optimal')),
                                'n_iter': int(getattr(one_shot_fit, 'n_iter', 0)),
                                'cycle_detected': False,
                                'outer_iterations': 1,
                                'termination': 'single_pass_realization_check',
                                'cycle_length': np.nan,
                                'marginal_count': 0,
                                'unaccounted_pair_count': int(len(one_shot_realized.unaccounted_pairs)),
                                'runtime_sec': one_runtime,
                                'warnings_fit': ' | '.join(one_shot_fit.warnings),
                                'warnings_realized': ' | '.join(one_shot_realized.warnings),
                            }
                        )

                        t0 = time.perf_counter()
                        refined = pyvoro2.solve_self_consistent_power_weights(
                            instance.base.points,
                            instance.observed_constraints,
                            measurement=instance.observed_constraints.measurement,
                            domain=instance.base.domain,
                            options=active_options,
                            fit_solver=fit_solver,
                            return_history=True,
                            connectivity_check='diagnose',
                            unaccounted_pair_check='diagnose',
                            tessellation_check='diagnose',
                        )
                        refine_runtime = float(time.perf_counter() - t0)
                        refine_selected = np.asarray(refined.active_mask, dtype=bool)
                        refine_metrics = mask_metrics(refine_selected, instance.true_realized_mask)
                        refine_predicted = np.asarray(refined.diagnostics.predicted, dtype=float)
                        refine_algebraic = algebraic_residual_metrics(
                            instance.observed_constraints,
                            np.asarray(refined.fit.weights, dtype=float),
                        )
                        rows.append(
                            base_row
                            | {
                                'method': 'self_consistent_refinement',
                                'selected_pair_count': int(refine_metrics.n_selected),
                                'true_positive_count': int(refine_metrics.true_positives),
                                'false_positive_count': int(refine_metrics.false_positives),
                                'false_negative_count': int(refine_metrics.false_negatives),
                                'selected_pair_precision': float(refine_metrics.precision),
                                'selected_pair_recall': float(refine_metrics.recall),
                                'selected_pair_f1': float(refine_metrics.f1),
                                'realized_selected_fraction': float(np.mean(refine_selected)),
                                'true_realized_separator_rmse': rmse_on_mask(refine_predicted, instance.observed_target, instance.true_realized_mask),
                                'all_candidate_separator_rmse': rmse_on_mask(
                                    refine_predicted,
                                    instance.observed_target,
                                    np.ones_like(instance.true_realized_mask, dtype=bool),
                                ),
                                'projection_residual_rmse': float(refine_algebraic.unweighted_rmse),
                                'status': refined.fit.status,
                                'status_detail': getattr(refined.fit, 'status_detail', None),
                                'solver': refined.fit.solver,
                                'converged': bool(refined.converged),
                                'n_iter': int(getattr(refined.fit, 'n_iter', 0)),
                                'cycle_detected': bool(refined.termination == 'cycle_detected'),
                                'outer_iterations': int(refined.n_outer_iter),
                                'termination': refined.termination,
                                'cycle_length': np.nan if refined.cycle_length is None else int(refined.cycle_length),
                                'marginal_count': int(len(refined.marginal_constraints)),
                                'unaccounted_pair_count': int(len(refined.realized.unaccounted_pairs)),
                                'runtime_sec': refine_runtime,
                                'warnings_fit': ' | '.join(refined.fit.warnings),
                                'warnings_realized': ' | '.join(refined.realized.warnings),
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
                'method_order': METHOD_ORDER,
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
