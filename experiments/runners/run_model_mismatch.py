#!/usr/bin/env python3
"""Run Experiment G: structured model-mismatch benchmarks."""
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
import pyvoro2.planar as pv2

if __package__ is None or __package__ == '':
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments._provenance import build_runtime_provenance  # noqa: E402
from experiments.generators.exact_recovery import (  # noqa: E402
    component_labels,
    componentwise_aligned_rmse,
    pair_difference_rmse,
)
from experiments.generators.model_mismatch import (  # noqa: E402
    make_model_mismatch_instance,
)
from experiments.generators.noise_robustness import (  # noqa: E402
    algebraic_residual_metrics,
    measurement_geometry,
    measurement_recovery_metrics,
)


LAW_ORDER = ['exact_control', 'type_cycle', 'local_context']


def _case_seed(base_seed: int, *parts: object) -> int:
    payload = '|'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, 'little') ^ int(base_seed)


def _smoke_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    cfg['replicates'] = 2
    cfg['n_sites_by_dimension'] = {2: [32], 3: [24]}
    cfg['laws']['type_cycle']['etas'] = [0.00, 0.20]
    cfg['laws']['local_context']['etas'] = [0.00, 0.20]
    return cfg


def _expand_n_sites(config: dict[str, Any]) -> dict[int, list[int]]:
    return {int(k): [int(v) for v in values] for k, values in config['n_sites_by_dimension'].items()}


def _configured_law_cases(config: dict[str, Any]) -> list[tuple[str, float]]:
    laws = config.get('laws', {})
    cases: list[tuple[str, float]] = []
    if laws.get('exact_control', {}).get('enabled', True):
        cases.append(('exact_control', 0.0))
    for name in ['type_cycle', 'local_context']:
        law_cfg = laws.get(name, {})
        if not law_cfg.get('enabled', True):
            continue
        for eta in law_cfg.get('etas', []):
            cases.append((name, float(eta)))
    return cases


def _support_edge_set(constraints: pyvoro2.PairBisectorConstraints) -> set[tuple[int, int]]:
    return {
        (min(int(i), int(j)), max(int(i), int(j)))
        for i, j in zip(constraints.i.tolist(), constraints.j.tolist(), strict=True)
    }


def _realized_edge_set(points: np.ndarray, radii: np.ndarray, domain: Any, *, dim: int) -> set[tuple[int, int]]:
    if dim == 2:
        cells = pv2.compute(points, domain=domain, mode='power', radii=np.asarray(radii, dtype=float), return_edges=True)
        items_key = 'edges'
    elif dim == 3:
        cells = pyvoro2.compute(points, domain=domain, mode='power', radii=np.asarray(radii, dtype=float), return_faces=True)
        items_key = 'faces'
    else:
        raise ValueError(f'unsupported dimension: {dim}')

    edge_set: set[tuple[int, int]] = set()
    for cell in cells:
        i = int(cell['id'])
        for item in cell[items_key]:
            j = int(item['adjacent_cell'])
            if j < 0:
                continue
            edge_set.add((min(i, j), max(i, j)))
    return edge_set


def _precision_recall_f1(truth: set[tuple[int, int]], pred: set[tuple[int, int]]) -> tuple[float, float, float]:
    if not truth and not pred:
        return 1.0, 1.0, 1.0
    tp = len(truth & pred)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(truth) if truth else 0.0
    if precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
    return float(precision), float(recall), float(f1)


def _fundamental_cycle_rms(constraints: pyvoro2.PairBisectorConstraints) -> tuple[float, int]:
    alpha, beta = measurement_geometry(constraints)
    z_obs = (np.asarray(constraints.target, dtype=float) - beta) / alpha
    n_points = int(constraints.n_points)
    edges = [(int(i), int(j)) for i, j in zip(constraints.i.tolist(), constraints.j.tolist(), strict=True)]

    adj: list[list[tuple[int, int, int]]] = [[] for _ in range(n_points)]
    for row_idx, (i, j) in enumerate(edges):
        adj[i].append((j, row_idx, +1))
        adj[j].append((i, row_idx, -1))

    parent = np.full(n_points, -1, dtype=int)
    potentials = np.zeros(n_points, dtype=float)
    tree_rows: set[int] = set()

    queue = [0]
    parent[0] = 0
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        for v, row_idx, sign in adj[u]:
            if parent[v] != -1:
                continue
            parent[v] = u
            potentials[v] = potentials[u] + sign * z_obs[row_idx]
            tree_rows.add(row_idx)
            queue.append(v)

    if np.any(parent == -1):
        raise ValueError('fundamental-cycle score expects a connected graph')

    defects: list[float] = []
    for row_idx, (i, j) in enumerate(edges):
        if row_idx in tree_rows:
            continue
        predicted = potentials[i] - potentials[j]
        defects.append(float(z_obs[row_idx] - predicted))

    if not defects:
        return 0.0, 0
    arr = np.asarray(defects, dtype=float)
    return float(np.sqrt(np.mean(arr * arr))), int(len(defects))


def _midpoint_prediction(constraints: pyvoro2.PairBisectorConstraints) -> np.ndarray:
    """Ordinary Voronoi midpoint baseline on a fixed candidate row set."""
    _alpha, beta = measurement_geometry(constraints)
    return np.asarray(beta, dtype=float)


def _relative_improvement(baseline_value: float, fit_value: float) -> float:
    if abs(float(baseline_value)) <= 1.0e-15:
        return 0.0 if abs(float(fit_value)) <= 1.0e-15 else float('nan')
    return float((baseline_value - fit_value) / baseline_value)


def _summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['geometry_family', 'dimension', 'n_sites', 'law_family', 'eta']
    return (
        df.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            n_constraints_mean=('n_constraints', 'mean'),
            clip_fraction_mean=('clip_fraction', 'mean'),
            measurement_rmse_mean=('measurement_rmse', 'mean'),
            measurement_mae_mean=('measurement_mae', 'mean'),
            midpoint_measurement_rmse_mean=('midpoint_measurement_rmse', 'mean'),
            midpoint_measurement_mae_mean=('midpoint_measurement_mae', 'mean'),
            measurement_rmse_gain_over_midpoint_mean=('measurement_rmse_gain_over_midpoint', 'mean'),
            projection_residual_rmse_mean=('projection_residual_rmse', 'mean'),
            projection_weighted_l2_mean=('projection_weighted_l2', 'mean'),
            midpoint_projection_residual_rmse_mean=('midpoint_projection_residual_rmse', 'mean'),
            cycle_rms_mean=('cycle_rms', 'mean'),
            realized_graph_precision_mean=('realized_graph_precision', 'mean'),
            realized_graph_recall_mean=('realized_graph_recall', 'mean'),
            realized_graph_f1_mean=('realized_graph_f1', 'mean'),
            midpoint_realized_graph_precision_mean=('midpoint_realized_graph_precision', 'mean'),
            midpoint_realized_graph_recall_mean=('midpoint_realized_graph_recall', 'mean'),
            midpoint_realized_graph_f1_mean=('midpoint_realized_graph_f1', 'mean'),
            realized_edge_count_mean=('realized_edge_count', 'mean'),
            midpoint_realized_edge_count_mean=('midpoint_realized_edge_count', 'mean'),
            edge_difference_rmse_mean=('edge_difference_rmse_to_exact', 'mean'),
            centered_weight_rmse_mean=('centered_weight_rmse_to_exact', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('experiments/configs/model_mismatch.yaml'))
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--smoke', action='store_true', help='Run a tiny CI/local smoke subset.')
    args = parser.parse_args()

    with args.config.open('r', encoding='utf-8') as fh:
        config = yaml.safe_load(fh)
    if args.smoke:
        config = _smoke_config(config)

    output_dir = Path(args.output_dir or config.get('output_dir', 'results/model_mismatch'))
    output_dir.mkdir(parents=True, exist_ok=True)

    clip_interval = tuple(float(v) for v in config.get('clip_interval', [0.05, 0.95]))
    rows: list[dict[str, Any]] = []

    for geometry_family in config.get('geometry_families', []):
        for dim in [int(v) for v in config.get('dimensions', [])]:
            for n_sites in _expand_n_sites(config).get(dim, []):
                for law_family, eta in _configured_law_cases(config):
                    for rep in range(int(config.get('replicates', 1))):
                        seed = _case_seed(config.get('seed', 0), 'G', geometry_family, dim, n_sites, law_family, eta, rep)
                        t0 = time.perf_counter()
                        instance = make_model_mismatch_instance(
                            n_sites=int(n_sites),
                            dim=int(dim),
                            geometry_family=str(geometry_family),
                            law_family=str(law_family),
                            eta=float(eta),
                            seed=int(seed),
                            weight_scale=float(config.get('weight_scale', 0.08)),
                            n_types=int(config.get('n_types', 3)),
                            k_neighbors=int(config.get('local_context_k', 4)),
                            clip_interval=clip_interval,
                        )
                        fit = pyvoro2.fit_power_weights(
                            instance.points,
                            instance.observed_constraints,
                            domain=instance.domain,
                            measurement='fraction',
                            solver=str(config.get('solver', 'analytic')),
                            connectivity_check='diagnose',
                        )
                        runtime_sec = float(time.perf_counter() - t0)

                        measurement_metrics = measurement_recovery_metrics(
                            instance.observed_target,
                            instance.observed_target,
                            np.asarray(fit.predicted, dtype=float),
                        )
                        algebraic_metrics = algebraic_residual_metrics(
                            instance.observed_constraints,
                            np.asarray(fit.weights, dtype=float),
                        )
                        cycle_rms, cycle_count = _fundamental_cycle_rms(instance.observed_constraints)

                        midpoint_predicted = _midpoint_prediction(instance.observed_constraints)
                        midpoint_measurement_metrics = measurement_recovery_metrics(
                            instance.observed_target,
                            instance.observed_target,
                            midpoint_predicted,
                        )
                        midpoint_algebraic_metrics = algebraic_residual_metrics(
                            instance.observed_constraints,
                            np.zeros(int(instance.observed_constraints.n_points), dtype=float),
                        )

                        exact_edges = _support_edge_set(instance.exact_constraints)
                        realized_edges = _realized_edge_set(
                            instance.points,
                            np.asarray(fit.radii, dtype=float),
                            instance.domain,
                            dim=int(dim),
                        )
                        graph_precision, graph_recall, graph_f1 = _precision_recall_f1(exact_edges, realized_edges)

                        midpoint_realized_edges = _realized_edge_set(
                            instance.points,
                            np.zeros(int(instance.observed_constraints.n_points), dtype=float),
                            instance.domain,
                            dim=int(dim),
                        )
                        midpoint_graph_precision, midpoint_graph_recall, midpoint_graph_f1 = _precision_recall_f1(
                            exact_edges,
                            midpoint_realized_edges,
                        )

                        labels = component_labels(
                            instance.exact_constraints.n_points,
                            list(zip(instance.exact_constraints.i.tolist(), instance.exact_constraints.j.tolist(), strict=True)),
                        )

                        rows.append(
                            {
                                'seed': int(seed),
                                'geometry_family': geometry_family,
                                'dimension': int(dim),
                                'n_sites': int(n_sites),
                                'law_family': law_family,
                                'eta': float(eta),
                                'n_constraints': int(instance.observed_constraints.n_constraints),
                                'clip_fraction': float(instance.clip_fraction),
                                'measurement_rmse': float(measurement_metrics.clean_rmse),
                                'measurement_mae': float(measurement_metrics.clean_mae),
                                'midpoint_measurement_rmse': float(midpoint_measurement_metrics.clean_rmse),
                                'midpoint_measurement_mae': float(midpoint_measurement_metrics.clean_mae),
                                'measurement_rmse_gain_over_midpoint': _relative_improvement(
                                    float(midpoint_measurement_metrics.clean_rmse),
                                    float(measurement_metrics.clean_rmse),
                                ),
                                'projection_residual_rmse': float(algebraic_metrics.unweighted_rmse),
                                'projection_weighted_l2': float(algebraic_metrics.weighted_l2),
                                'projection_weighted_rmse': float(algebraic_metrics.weighted_rmse),
                                'midpoint_projection_residual_rmse': float(midpoint_algebraic_metrics.unweighted_rmse),
                                'cycle_rms': float(cycle_rms),
                                'cycle_count': int(cycle_count),
                                'realized_graph_precision': float(graph_precision),
                                'realized_graph_recall': float(graph_recall),
                                'realized_graph_f1': float(graph_f1),
                                'realized_edge_count': int(len(realized_edges)),
                                'midpoint_realized_graph_precision': float(midpoint_graph_precision),
                                'midpoint_realized_graph_recall': float(midpoint_graph_recall),
                                'midpoint_realized_graph_f1': float(midpoint_graph_f1),
                                'midpoint_realized_edge_count': int(len(midpoint_realized_edges)),
                                'edge_difference_rmse_to_exact': float(
                                    pair_difference_rmse(
                                        np.asarray(instance.true_weights, dtype=float),
                                        np.asarray(fit.weights, dtype=float),
                                        instance.exact_constraints,
                                    )
                                ),
                                'centered_weight_rmse_to_exact': float(
                                    componentwise_aligned_rmse(
                                        np.asarray(instance.true_weights, dtype=float),
                                        np.asarray(fit.weights, dtype=float),
                                        labels,
                                    )
                                ),
                                'runtime_sec': runtime_sec,
                                'solver': str(getattr(fit, 'solver', 'unknown')),
                                'status': str(getattr(fit, 'status', 'unknown')),
                                'converged': bool(getattr(fit, 'converged', getattr(fit, 'status', '') == 'optimal')),
                                'n_iter': int(getattr(fit, 'n_iter', 0)),
                                'warnings_fit': ' | '.join(getattr(fit, 'warnings', [])),
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
                'law_cases': _configured_law_cases(config),
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
