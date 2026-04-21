#!/usr/bin/env python3
"""Aggregate Experiment H outputs into manuscript-facing summaries."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


METHOD_ORDER = ['one_shot_fit', 'self_consistent_refinement']


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['method', 'candidate_graph', 'dimension', 'n_sites', 'law_family', 'eta']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            candidate_parameter_mean=('candidate_parameter', 'mean'),
            clip_fraction_mean=('clip_fraction', 'mean'),
            candidate_pair_count_mean=('candidate_pair_count', 'mean'),
            extra_pair_count_mean=('extra_pair_count', 'mean'),
            selected_pair_precision_mean=('selected_pair_precision', 'mean'),
            selected_pair_recall_mean=('selected_pair_recall', 'mean'),
            selected_pair_f1_mean=('selected_pair_f1', 'mean'),
            true_realized_separator_rmse_mean=('true_realized_separator_rmse', 'mean'),
            all_candidate_separator_rmse_mean=('all_candidate_separator_rmse', 'mean'),
            projection_residual_rmse_mean=('projection_residual_rmse', 'mean'),
            outer_iterations_mean=('outer_iterations', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def _trend_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['method', 'candidate_graph', 'dimension', 'law_family', 'eta']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            clip_fraction_mean=('clip_fraction', 'mean'),
            selected_pair_f1_mean=('selected_pair_f1', 'mean'),
            true_realized_separator_rmse_mean=('true_realized_separator_rmse', 'mean'),
            projection_residual_rmse_mean=('projection_residual_rmse', 'mean'),
            outer_iterations_mean=('outer_iterations', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/supergraph_mismatch/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/supergraph_mismatch/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    trends = _trend_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')
    trends.to_csv(args.output_dir / 'trend_summary.csv', index=False)
    trends.to_latex(args.output_dir / 'trend_summary.tex', index=False, float_format='%.3e')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
