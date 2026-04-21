#!/usr/bin/env python3
"""Run Experiment C: missing data and sparsity."""
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
from experiments.generators.missing_data import (  # noqa: E402
    graph_metrics,
    make_missing_data_instance,
    recovery_metrics,
)


def _case_seed(base_seed: int, *parts: object) -> int:
    payload = '|'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'little') ^ int(base_seed)


def _expand_n_sites(config: dict[str, Any]) -> dict[int, list[int]]:
    raw = config['n_sites_by_dimension']
    return {int(key): [int(v) for v in values] for key, values in raw.items()}


def _smoke_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    cfg['replicates'] = min(int(cfg.get('replicates', 1)), 3)
    cfg['dimensions'] = [2, 3]
    cfg['n_sites_by_dimension'] = {2: [16], 3: [24]}
    cfg['edge_keep_fractions'] = [1.0, 0.75, 0.5, 0.3, 0.15]
    return cfg


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['dimension', 'n_sites', 'keep_fraction_requested']
    return (
        df.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            keep_fraction_actual_mean=('keep_fraction_actual', 'mean'),
            base_generation_attempts_mean=('base_generation_attempts', 'mean'),
            n_constraints_full_mean=('n_constraints_full', 'mean'),
            n_constraints_observed_mean=('n_constraints_observed', 'mean'),
            connected_rate=('connected', 'mean'),
            n_components_mean=('n_components', 'mean'),
            largest_component_fraction_mean=('largest_component_fraction', 'mean'),
            recoverable_pair_fraction_mean=('recoverable_pair_fraction', 'mean'),
            isolated_site_fraction_mean=('isolated_site_fraction', 'mean'),
            observed_separator_rmse_mean=('observed_separator_rmse', 'mean'),
            observed_separator_rmse_max=('observed_separator_rmse', 'max'),
            componentwise_aligned_weight_rmse_mean=('componentwise_aligned_weight_rmse', 'mean'),
            global_centered_weight_rmse_mean=('global_centered_weight_rmse', 'mean'),
            all_pair_difference_rmse_mean=('all_pair_difference_rmse', 'mean'),
            same_component_pair_difference_rmse_mean=('same_component_pair_difference_rmse', 'mean'),
            component_shift_std_mean=('component_shift_std', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/missing_data.yaml'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = Path(args.output_dir or config.get('output_dir', 'results/missing_data'))
    output_dir.mkdir(parents=True, exist_ok=True)

    measurement = str(config.get('measurement', 'fraction'))
    weight_scale = float(config.get('weight_scale', 0.08))
    max_base_generation_attempts = int(config.get('max_base_generation_attempts', 50))
    rows: list[dict[str, Any]] = []

    for dim in [int(d) for d in config.get('dimensions', [])]:
        for n_sites in _expand_n_sites(config).get(dim, []):
            for keep_fraction in [float(v) for v in config.get('edge_keep_fractions', [])]:
                for rep in range(int(config.get('replicates', 1))):
                    seed = _case_seed(int(config.get('seed', 0)), 'C', dim, n_sites, keep_fraction, rep)
                    instance = make_missing_data_instance(
                        n_sites=int(n_sites),
                        dim=int(dim),
                        seed=seed,
                        keep_fraction=float(keep_fraction),
                        measurement=measurement,
                        weight_scale=weight_scale,
                        max_base_generation_attempts=max_base_generation_attempts,
                    )
                    t0 = time.perf_counter()
                    fit = pyvoro2.fit_power_weights(
                        instance.base.points,
                        instance.observed_resolved_constraints,
                        domain=instance.base.domain,
                        measurement=instance.base.measurement,
                        solver=str(config.get('solver', 'analytic')),
                        connectivity_check='diagnose',
                    )
                    runtime_sec = float(time.perf_counter() - t0)

                    labels = np.asarray(instance.observed_component_labels, dtype=int)
                    graph = graph_metrics(labels)
                    rec = recovery_metrics(
                        instance.base.true_weights,
                        np.asarray(fit.weights, dtype=float),
                        labels,
                    )
                    observed_target = np.asarray(instance.observed_resolved_constraints.target, dtype=float)
                    predicted = np.asarray(fit.predicted, dtype=float)
                    observed_separator_rmse = float(np.sqrt(np.mean((predicted - observed_target) ** 2)))

                    rows.append(
                        {
                            'seed': seed,
                            'dimension': dim,
                            'n_sites': int(n_sites),
                            'keep_fraction_requested': float(keep_fraction),
                            'keep_fraction_actual': float(instance.keep_fraction_actual),
                            'measurement': instance.base.measurement,
                            'base_generation_attempts': int(instance.base_generation_attempts),
                            'n_constraints_full': int(instance.base.resolved_constraints.n_constraints),
                            'n_constraints_observed': int(instance.observed_resolved_constraints.n_constraints),
                            'connected': bool(graph.connected),
                            'n_components': int(graph.n_components),
                            'largest_component_fraction': float(graph.largest_component_fraction),
                            'recoverable_pair_fraction': float(graph.recoverable_pair_fraction),
                            'isolated_site_fraction': float(graph.isolated_site_fraction),
                            'observed_separator_rmse': observed_separator_rmse,
                            'componentwise_aligned_weight_rmse': float(rec.componentwise_aligned_weight_rmse),
                            'global_centered_weight_rmse': float(rec.global_centered_weight_rmse),
                            'all_pair_difference_rmse': float(rec.all_pair_difference_rmse),
                            'same_component_pair_difference_rmse': float(rec.same_component_pair_difference_rmse),
                            'component_shift_std': float(rec.component_shift_std),
                            'status': fit.status,
                            'status_detail': getattr(fit, 'status_detail', None),
                            'solver': fit.solver,
                            'converged': bool(getattr(fit, 'converged', fit.status == 'optimal')),
                            'n_iter': int(getattr(fit, 'n_iter', 0)),
                            'fit_rms_residual': float(fit.rms_residual),
                            'fit_max_residual': float(fit.max_residual),
                            'runtime_sec': runtime_sec,
                            'warnings_fit': ' | '.join(fit.warnings),
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
