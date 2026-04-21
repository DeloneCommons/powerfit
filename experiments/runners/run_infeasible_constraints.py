#!/usr/bin/env python3
"""Run Experiment D: infeasible hard constraints."""
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
from experiments.generators.infeasible_constraints import (  # noqa: E402
    edge_difference_rmse,
    make_infeasible_constraint_instance,
    solve_difference_bounds,
    support_diagnostics,
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
    return cfg


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['scenario', 'dimension', 'n_sites']
    infeasible = ~df['feasible_expected']
    feasible = df['feasible_expected']

    def mean_on(mask: pd.Series, column: str) -> pd.Series:
        return (
            df.loc[mask, group_cols + [column]]
            .groupby(group_cols, dropna=False)[column]
            .mean()
        )

    summary = (
        df.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            feasible_expected_rate=('feasible_expected', 'mean'),
            feasible_detected_rate=('feasible_detected', 'mean'),
            detection_correct_rate=('detection_correct', 'mean'),
            support_cycle_length_mean=('support_cycle_length', 'mean'),
            support_n_nodes_mean=('support_n_nodes', 'mean'),
            support_target_min_mean=('support_target_min', 'mean'),
            support_target_max_mean=('support_target_max', 'mean'),
            generation_attempts_mean=('generation_attempts', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )

    summary = summary.merge(
        mean_on(infeasible, 'witness_term_count').rename('witness_term_count_mean').reset_index(),
        on=group_cols,
        how='left',
    )
    summary = summary.merge(
        mean_on(infeasible, 'negative_cycle_margin').rename('negative_cycle_margin_mean').reset_index(),
        on=group_cols,
        how='left',
    )
    summary = summary.merge(
        mean_on(feasible, 'edge_difference_rmse_to_true').rename('edge_difference_rmse_to_true_mean').reset_index(),
        on=group_cols,
        how='left',
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--config',
        type=Path,
        default=Path('experiments/configs/infeasible_constraints.yaml'),
    )
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = Path(args.output_dir or config.get('output_dir', 'results/infeasible'))
    output_dir.mkdir(parents=True, exist_ok=True)

    measurement = str(config.get('measurement', 'fraction'))
    weight_scale = float(config.get('weight_scale', 0.08))
    interval_halfwidth = float(config.get('interval_halfwidth', 0.01))
    contradiction_shift = float(config.get('contradiction_shift', 0.06))
    between_points_interval = tuple(float(v) for v in config.get('between_points_interval', [0.0, 1.0]))
    max_generation_attempts = int(config.get('max_generation_attempts', 80))
    rows: list[dict[str, Any]] = []

    for dim in [int(d) for d in config.get('dimensions', [])]:
        for n_sites in _expand_n_sites(config).get(dim, []):
            for scenario in [str(v) for v in config.get('scenarios', [])]:
                for rep in range(int(config.get('replicates', 1))):
                    seed = _case_seed(int(config.get('seed', 0)), 'D', dim, n_sites, scenario, rep)
                    instance = make_infeasible_constraint_instance(
                        scenario=scenario,
                        n_sites=int(n_sites),
                        dim=int(dim),
                        seed=seed,
                        measurement=measurement,
                        weight_scale=weight_scale,
                        interval_halfwidth=interval_halfwidth,
                        contradiction_shift=contradiction_shift,
                        between_points_interval=between_points_interval,
                        max_generation_attempts=max_generation_attempts,
                    )
                    diag = support_diagnostics(instance)
                    t0 = time.perf_counter()
                    result = solve_difference_bounds(
                        int(instance.base.resolved_constraints.n_points),
                        np.asarray(instance.support_constraints.i, dtype=int),
                        np.asarray(instance.support_constraints.j, dtype=int),
                        np.asarray(instance.difference_lower, dtype=float),
                        np.asarray(instance.difference_upper, dtype=float),
                    )
                    runtime_sec = float(time.perf_counter() - t0)

                    feasible_detected = bool(result.feasible)
                    detection_correct = bool(feasible_detected == instance.feasible_expected)
                    witness_term_count = (
                        np.nan
                        if result.conflict is None
                        else float(len(result.conflict.terms))
                    )
                    negative_cycle_margin = (
                        np.nan
                        if result.conflict is None
                        else float(-result.conflict.cycle_total)
                    )
                    edge_rmse = (
                        float(edge_difference_rmse(
                            instance.base.true_weights,
                            np.asarray(result.weights, dtype=float),
                            instance.support_constraints,
                        ))
                        if result.feasible and result.weights is not None
                        else np.nan
                    )
                    perturbed_global = (
                        np.nan
                        if instance.perturbed_local_index is None
                        else float(instance.support_row_indices_global[int(instance.perturbed_local_index)])
                    )
                    conflict_rows = (
                        ''
                        if result.conflict is None
                        else '|'.join(
                            str(int(term.constraint_index)) for term in result.conflict.terms
                        )
                    )
                    rows.append(
                        {
                            'seed': seed,
                            'scenario': instance.scenario,
                            'scenario_group': 'feasible' if instance.feasible_expected else 'infeasible',
                            'feasible_expected': bool(instance.feasible_expected),
                            'feasible_detected': feasible_detected,
                            'detection_correct': detection_correct,
                            'dimension': int(dim),
                            'n_sites': int(n_sites),
                            'measurement': instance.support_constraints.measurement,
                            'support_n_constraints': int(diag.n_support_constraints),
                            'support_n_nodes': int(diag.n_support_nodes),
                            'support_cycle_length': int(diag.cycle_length),
                            'support_target_min': float(diag.support_target_min),
                            'support_target_max': float(diag.support_target_max),
                            'support_has_outside_fraction_edge': bool(diag.has_outside_fraction_edge),
                            'support_outside_fraction_edge_count': int(diag.outside_fraction_edge_count),
                            'generation_attempts': int(instance.generation_attempts),
                            'perturbed_local_index': (
                                np.nan if instance.perturbed_local_index is None else int(instance.perturbed_local_index)
                            ),
                            'perturbed_global_index': perturbed_global,
                            'note': instance.note,
                            'min_measurement_lower': float(np.min(instance.measurement_lower)),
                            'max_measurement_upper': float(np.max(instance.measurement_upper)),
                            'min_difference_lower': float(np.min(instance.difference_lower)),
                            'max_difference_upper': float(np.max(instance.difference_upper)),
                            'max_violation': (
                                np.nan if result.max_violation is None else float(result.max_violation)
                            ),
                            'min_lower_slack': (
                                np.nan if result.min_lower_slack is None else float(result.min_lower_slack)
                            ),
                            'min_upper_slack': (
                                np.nan if result.min_upper_slack is None else float(result.min_upper_slack)
                            ),
                            'edge_difference_rmse_to_true': edge_rmse,
                            'witness_term_count': witness_term_count,
                            'witness_cycle_node_count': (
                                np.nan if result.conflict is None else float(len(result.conflict.cycle_nodes))
                            ),
                            'negative_cycle_margin': negative_cycle_margin,
                            'conflict_rows_local': conflict_rows,
                            'runtime_sec': runtime_sec,
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
