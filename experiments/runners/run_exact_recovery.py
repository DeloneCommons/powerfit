#!/usr/bin/env python3
"""Run exact-recovery benchmarks for the manuscript."""
from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import yaml

import pyvoro2

# Allow running as a script from the repository root.
if __package__ is None or __package__ == '':
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments._provenance import build_runtime_provenance  # noqa: E402
from experiments.generators.exact_recovery import (  # noqa: E402
    component_labels,
    componentwise_aligned_rmse,
    make_exact_recovery_instance,
    pair_difference_rmse,
)


def _case_seed(base_seed: int, *parts: object) -> int:
    payload = '|'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'little') ^ int(base_seed)


def _expand_n_sites(config: dict) -> dict[int, list[int]]:
    if 'n_sites_by_dimension' in config:
        return {int(k): [int(vv) for vv in v] for k, v in config['n_sites_by_dimension'].items()}
    values = [int(v) for v in config['n_sites']]
    return {int(dim): values for dim in config['dimensions']}


def _smoke_config(config: dict) -> dict:
    cfg = json.loads(json.dumps(config))
    cfg['replicates'] = min(int(cfg.get('replicates', 1)), 2)
    cfg['dimensions'] = [2, 3]
    cfg['periodic'] = [False, True]
    cfg['graph_variants'] = ['full_realized', 'two_component_subgraph']
    cfg['n_sites_by_dimension'] = {2: [16], 3: [24]}
    return cfg


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['dimension', 'periodic', 'graph_variant', 'n_sites']
    agg_map: dict[str, tuple[str, str]] = {
        'runs': ('seed', 'count'),
        'n_constraints_mean': ('n_constraints', 'mean'),
        'n_components_mean': ('n_components', 'mean'),
        'separator_rmse_mean': ('separator_rmse', 'mean'),
        'separator_rmse_max': ('separator_rmse', 'max'),
        'edge_difference_rmse_mean': ('edge_difference_rmse', 'mean'),
        'centered_weight_rmse_mean': ('centered_weight_rmse', 'mean'),
        'realized_same_shift_recall_mean': ('realized_same_shift_recall', 'mean'),
        'realized_any_recall_mean': ('realized_any_recall', 'mean'),
        'runtime_sec_mean': ('runtime_sec', 'mean'),
    }
    optional = {
        'algebraic_inconsistency_mean': 'algebraic_inconsistency',
        'algebraic_residual_rmse_mean': 'algebraic_residual_rmse',
        'edge_weighted_rmse_mean': 'edge_weighted_rmse',
    }
    for outcol, incol in optional.items():
        if incol in df.columns:
            agg_map[outcol] = (incol, 'mean')
    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(**agg_map)
        .reset_index()
        .sort_values(group_cols)
    )
    return agg


def _edge_diag_values(fit) -> tuple[float, float, float]:
    diag = getattr(fit, 'edge_diagnostics', None)
    if diag is None:
        return float('nan'), float('nan'), float('nan')
    weighted_l2 = float(diag.weighted_l2) if diag.weighted_l2 is not None else float('nan')
    rmse = float(diag.rmse) if diag.rmse is not None else float('nan')
    weighted_rmse = float(diag.weighted_rmse) if diag.weighted_rmse is not None else float('nan')
    return weighted_l2, rmse, weighted_rmse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/exact_recovery.yaml'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = args.output_dir or Path(config.get('output_dir', 'results/exact_recovery'))
    output_dir.mkdir(parents=True, exist_ok=True)

    n_sites_by_dim = _expand_n_sites(config)
    rows: list[dict[str, object]] = []

    for dim in [int(v) for v in config['dimensions']]:
        for periodic in [bool(v) for v in config['periodic']]:
            for n_sites in n_sites_by_dim[dim]:
                for graph_variant in config.get('graph_variants', ['full_realized']):
                    for rep in range(int(config.get('replicates', 1))):
                        seed = _case_seed(config.get('seed', 0), dim, periodic, n_sites, graph_variant, rep)
                        t0 = time.perf_counter()
                        instance = make_exact_recovery_instance(
                            n_sites=int(n_sites),
                            dim=dim,
                            periodic=periodic,
                            seed=seed,
                            graph_variant=str(graph_variant),
                            measurement=str(config.get('measurement', 'fraction')),
                            weight_scale=float(config.get('weight_scale', 0.08)),
                            validate_periodic_planar_shifts=bool(config.get('validate_periodic_planar_shifts', False)),
                        )
                        fit = pyvoro2.fit_power_weights(
                            instance.points,
                            instance.resolved_constraints,
                            domain=instance.domain,
                            measurement=instance.measurement,
                            image='given_only' if periodic else 'nearest',
                            solver=str(config.get('solver', 'analytic')),
                            connectivity_check='diagnose',
                        )
                        realized = pyvoro2.match_realized_pairs(
                            instance.points,
                            domain=instance.domain,
                            radii=fit.radii,
                            constraints=instance.resolved_constraints,
                        )
                        runtime_sec = time.perf_counter() - t0

                        labels = component_labels(
                            instance.resolved_constraints.n_points,
                            list(zip(instance.resolved_constraints.i.tolist(), instance.resolved_constraints.j.tolist(), strict=True)),
                        )
                        separator_rmse = float(np.sqrt(np.mean((fit.predicted - instance.resolved_constraints.target) ** 2)))
                        edge_rmse = pair_difference_rmse(instance.true_weights, fit.weights, instance.resolved_constraints)
                        centered_rmse = componentwise_aligned_rmse(instance.true_weights, fit.weights, labels)
                        realized_same = float(np.mean(realized.realized_same_shift))
                        realized_any = float(np.mean(realized.realized))
                        algebraic_inconsistency, algebraic_rmse, edge_weighted_rmse = _edge_diag_values(fit)

                        rows.append(
                            {
                                'seed': seed,
                                'dimension': dim,
                                'periodic': periodic,
                                'n_sites': int(n_sites),
                                'graph_variant': graph_variant,
                                'solver': fit.solver,
                                'status': fit.status,
                                'status_detail': getattr(fit, 'status_detail', None),
                                'converged': bool(getattr(fit, 'converged', fit.status == 'optimal')),
                                'n_iter': int(getattr(fit, 'n_iter', 0)),
                                'n_constraints': int(instance.resolved_constraints.n_constraints),
                                'n_components': int(labels.max() + 1),
                                'separator_rmse': separator_rmse,
                                'edge_difference_rmse': edge_rmse,
                                'centered_weight_rmse': centered_rmse,
                                'algebraic_inconsistency': algebraic_inconsistency,
                                'algebraic_residual_rmse': algebraic_rmse,
                                'edge_weighted_rmse': edge_weighted_rmse,
                                'realized_same_shift_recall': realized_same,
                                'realized_any_recall': realized_any,
                                'fit_rms_residual': float(fit.rms_residual),
                                'fit_max_residual': float(fit.max_residual),
                                'runtime_sec': runtime_sec,
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
