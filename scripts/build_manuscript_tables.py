#!/usr/bin/env python3
"""Build manuscript table fragments for the archived experiment outputs."""
from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / 'manuscript' / 'tables'
OUTDIR.mkdir(parents=True, exist_ok=True)


def _write_fragment(stem: str, text: str) -> None:
    (OUTDIR / f'{stem}.tex').write_text(text, encoding='utf-8')


def _render_table(
    df: pd.DataFrame,
    *,
    columns: list[str],
    align: str,
    caption: str,
    label: str,
    stem: str,
    placement: str = 'H',
    resize: bool = True,
    size_cmd: str = r'\small',
    tabcolsep_pt: int = 4,
    arraystretch: float = 1.05,
) -> None:
    body = df.to_latex(
        index=False,
        escape=False,
        float_format=lambda x: f'{x:.3g}',
        column_format=align,
        header=columns,
    )
    begin = r'\begin{tabular}'
    end = r'\end{tabular}'
    start = body.index(begin)
    stop = body.index(end) + len(end)
    tabular = body[start:stop]
    parts = [
        rf'\begin{{table}}[{placement}]',
        f'\\caption{{{caption}}}',
        f'\\label{{{label}}}',
        r'\centering',
        size_cmd,
        rf'\setlength{{\tabcolsep}}{{{tabcolsep_pt}pt}}',
        rf'\renewcommand{{\arraystretch}}{{{arraystretch}}}',
    ]
    if resize:
        parts += [r'\resizebox{\textwidth}{!}{%', tabular, r'}']
    else:
        parts += [tabular]
    parts += [r'\end{table}', '']
    _write_fragment(stem, '\n'.join(parts))


def _fmt_sci(x: float) -> str:
    if x == 0:
        return '0'
    exp = int(np.floor(np.log10(abs(x))))
    mant = x / (10 ** exp)
    return rf'{mant:.2g}\times 10^{{{exp}}}'




def table_a() -> None:
    df = pd.read_csv(ROOT / 'results/exact_recovery/summary.csv')
    out = pd.DataFrame(
        {
            'dim': df['dimension'],
            'periodic': df['periodic'].map({True: 'yes', False: 'no'}),
            'graph': df['graph_variant'].map(
                {
                    'full_realized': 'full realized',
                    'two_component_subgraph': 'two-component subgraph',
                }
            ),
            'n': df['n_sites'],
            'sep. RMSE': df['separator_rmse_mean'],
            'edge-diff RMSE': df['edge_difference_rmse_mean'],
            'wt. RMSE': df['centered_weight_rmse_mean'],
            'recall': df['realized_any_recall_mean'],
            'time (ms)': 1e3 * df['runtime_sec_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='rllrrrrrr',
        caption=(
            'Experiment A: exact recovery from realized-pair inputs. '
            'The disconnected two-component subgraph cases retain exact within-component '
            'reconstruction but lose global anchoring.'
        ),
        label='tab:exact_recovery',
        stem='table_A_exact_recovery',
    )


def table_b() -> None:
    df = pd.read_csv(ROOT / 'results/noise_robustness/summary.csv')
    dense = df[df['noise_family'].isin(['gaussian', 'laplace']) & (df['method'] == 'squared')]
    outlier = df[df['noise_family'] == 'outlier']
    df = pd.concat([dense, outlier], ignore_index=True)
    family_order = {'gaussian': 0, 'laplace': 1, 'outlier': 2}
    method_order = {'squared': 0, 'huber': 1}
    df = (
        df.assign(
            _family_order=df['noise_family'].map(family_order).fillna(99),
            _method_order=df['method'].map(method_order).fillna(99),
        )
        .sort_values(['dimension', 'n_sites', '_family_order', 'outlier_fraction', 'noise_level', '_method_order'])
        .drop(columns=['_family_order', '_method_order'])
        .reset_index(drop=True)
    )

    def noise_label(row: pd.Series) -> str:
        fam = row['noise_family']
        lvl = row['noise_level']
        if fam == 'outlier':
            return f'outlier amp={row["outlier_amplitude"]:.3f}, frac={row["outlier_fraction"]:.2f}'
        return f'{fam} $\\sigma$={lvl:.3f}'

    out = pd.DataFrame(
        {
            'dim': df['dimension'],
            'n': df['n_sites'],
            'noise setting': df.apply(noise_label, axis=1),
            'method': df['method'].map({'squared': 'squared', 'huber': 'Huber'}),
            'sep. RMSE': df['clean_separator_rmse_mean'],
            'edge-diff RMSE': df['edge_difference_rmse_mean'],
            'alg. resid. RMSE': df['algebraic_residual_rmse_mean'],
            'recall': df['realized_any_recall_mean'],
            'time (ms)': 1e3 * df['runtime_sec_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='rrllrrrrr',
        caption=(
            'Experiment B: noise and contamination response on correct candidate graphs. '
            'Dense Gaussian/Laplace controls are shown for the squared fit, whereas sparse-outlier rows compare squared and Huber fitting on the same exact support.'
        ),
        label='tab:noise_response',
        stem='table_B_noise_response',
    )


def table_d() -> None:
    df = pd.read_csv(ROOT / 'results/infeasible/summary.csv')
    scenario_map = {
        'exact_equalities': 'exact equalities',
        'narrow_intervals': 'narrow intervals',
        'contradictory_equalities': 'contradictory equalities',
        'contradictory_intervals': 'contradictory intervals',
        'between_points_violation': 'between-points violation',
    }
    out = pd.DataFrame(
        {
            'scenario': df['scenario'].map(scenario_map),
            'dim': df['dimension'],
            'n': df['n_sites'],
            'detected feasible': df['feasible_detected_rate'].map(lambda x: '--' if pd.isna(x) else x),
            'detection correct': df['detection_correct_rate'],
            'witness terms': df['witness_term_count_mean'].map(lambda x: '--' if pd.isna(x) else x),
            'neg.-cycle margin': df['negative_cycle_margin_mean'].map(lambda x: '--' if pd.isna(x) else x),
            'time (ms)': 1e3 * df['runtime_sec_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='lrrrrrrr',
        caption=(
            'Experiment D: feasibility detection for hard equality and interval restrictions, '
            'including contradiction witnesses for infeasible cases.'
        ),
        label='tab:infeasible_constraints',
        stem='table_D_infeasible_constraints',
    )


def table_e() -> None:
    df = pd.read_csv(ROOT / 'results/active_set/summary.csv')
    out = pd.DataFrame(
        {
            'method': df['method'].map(
                {
                    'one_shot_fit': 'one-shot fit',
                    'self_consistent_refinement': 'self-consistent refinement',
                }
            ),
            'candidate graph': df['candidate_graph'].map(
                {
                    'knn_supergraph': 'kNN supergraph',
                    'radius_supergraph': 'radius supergraph',
                }
            ),
            'dim': df['dimension'],
            'n': df['n_sites'],
            'cand. pairs': df['candidate_pair_count_mean'],
            'F1': df['selected_pair_f1_mean'],
            'true-row sep. RMSE': df['true_realized_separator_rmse_mean'],
            'outer iters': df['outer_iterations_mean'],
            'time (ms)': 1e3 * df['runtime_sec_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='llrrrrrrr',
        caption='Experiment E: realization-aware active-set refinement on strict supergraph inputs.',
        label='tab:active_set_refinement',
        stem='table_E_active_set',
    )


def table_f() -> None:
    df = pd.read_csv(ROOT / 'results/periodic/summary.csv')
    scenario_map = {
        'correct_images': 'correct images',
        'noisy_correct_images': 'noisy correct images',
        'wrong_images_authoritative': 'authoritative wrong images',
        'nearest_image_inference': 'nearest-image inference',
        'realized_shift_refinement': 'realized-shift refinement',
    }
    scenario_order = {
        'correct_images': 0,
        'noisy_correct_images': 1,
        'wrong_images_authoritative': 2,
        'nearest_image_inference': 3,
        'realized_shift_refinement': 4,
    }
    controls = df[df['scenario'].isin(['correct_images', 'noisy_correct_images'])]
    authoritative = df[df['scenario'] == 'wrong_images_authoritative']
    repair = (
        df[df['scenario'].isin(['nearest_image_inference', 'realized_shift_refinement'])]
        .sort_values(['dimension', 'n_sites', 'scenario', 'corruption_fraction'])
        .drop_duplicates(['dimension', 'n_sites', 'scenario'], keep='first')
        .copy()
    )
    repair['corruption_fraction'] = np.nan
    df = pd.concat([controls, authoritative, repair], ignore_index=True)
    df = (
        df.assign(_scenario_order=df['scenario'].map(scenario_order).fillna(99))
        .sort_values(['dimension', 'n_sites', '_scenario_order', 'corruption_fraction'])
        .drop(columns=['_scenario_order'])
        .reset_index(drop=True)
    )
    out = pd.DataFrame(
        {
            'scenario': df['scenario'].map(scenario_map),
            'dim': df['dimension'],
            'n': df['n_sites'],
            'corr. frac.': df['corruption_fraction'].map(lambda x: '--' if pd.isna(x) else x),
            'image acc.': df['image_choice_accuracy_mean'],
            'other-shift': df['realized_other_shift_rate_mean'],
            'sep. RMSE': df['clean_separator_rmse_mean'],
            'pair-diff RMSE': df['pair_difference_rmse_mean'],
            'iters': df['shift_refinement_iterations_mean'].map(lambda x: '--' if pd.isna(x) else x),
            'time (ms)': 1e3 * df['runtime_sec_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='lrrrrrrrrr',
        caption=(
            'Experiment F: periodic wrong-image diagnostics and repair across multiple authoritative corruption fractions. '
            'Controls are shown at zero corruption; authoritative wrong-image rows are swept over the corruption fraction; nearest-image inference and realized-shift refinement are shift-stripped repair baselines and therefore appear once per dimension.'
        ),
        label='tab:periodic_cases',
        stem='table_F_periodic',
    )


def table_g() -> None:
    df = pd.read_csv(ROOT / 'results/model_mismatch/summary.csv')
    df = df[(df['law_family'] != 'exact_control') & np.isclose(df['eta'], 0.20)].copy()
    family_order = {'type_cycle': 0, 'local_context': 1}
    geometry_order = {'hard_core_random': 0, 'perturbed_lattice': 1}
    df = (
        df.assign(
            _law=df['law_family'].map(family_order).fillna(99),
            _geom=df['geometry_family'].map(geometry_order).fillna(99),
        )
        .sort_values(['dimension', '_geom', '_law', 'n_sites'])
        .drop(columns=['_law', '_geom'])
        .reset_index(drop=True)
    )
    out = pd.DataFrame(
        {
            'geometry': df['geometry_family'].map(
                {'hard_core_random': 'hard-core random', 'perturbed_lattice': 'perturbed lattice'}
            ),
            'dim': df['dimension'],
            'n': df['n_sites'],
            'law': df['law_family'].map({'type_cycle': 'type-cycle', 'local_context': 'local-context'}),
            'fit RMSE': df['measurement_rmse_mean'],
            'mid. RMSE': df['midpoint_measurement_rmse_mean'],
            'gain (\\%)': 100.0 * df['measurement_rmse_gain_over_midpoint_mean'],
            'proj. RMSE': df['projection_residual_rmse_mean'],
            'fit F1': df['realized_graph_f1_mean'],
            'midpoint F1': df['midpoint_realized_graph_f1_mean'],
            'clip': df['clip_fraction_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='lrrlrrrrrrr',
        caption=(
            'Experiment G: structured model mismatch on exact support at representative moderate mismatch $\\eta=0.20$. '
            'The inverse fit is compared with the ordinary Voronoi midpoint baseline; the projection residual reports the compatibility defect of the imposed row data.'
        ),
        label='tab:model_mismatch',
        stem='table_G_model_mismatch',
    )


def table_h() -> None:
    df = pd.read_csv(ROOT / 'results/supergraph_mismatch/summary.csv')
    df = df[df['eta'].isin([0.00, 0.20, 0.40])].copy()
    method_map = {
        'one_shot_fit': 'one-shot fit',
        'self_consistent_refinement': 'self-consistent refinement',
    }
    graph_map = {
        'knn_supergraph': 'kNN supergraph',
        'radius_supergraph': 'radius supergraph',
    }
    method_order = {'one_shot_fit': 0, 'self_consistent_refinement': 1}
    graph_order = {'knn_supergraph': 0, 'radius_supergraph': 1}
    df = (
        df.assign(
            _method=df['method'].map(method_order).fillna(99),
            _graph=df['candidate_graph'].map(graph_order).fillna(99),
        )
        .sort_values(['dimension', '_graph', 'eta', '_method'])
        .drop(columns=['_method', '_graph'])
        .reset_index(drop=True)
    )
    out = pd.DataFrame(
        {
            'method': df['method'].map(method_map),
            'candidate graph': df['candidate_graph'].map(graph_map),
            'dim': df['dimension'],
            'n': df['n_sites'],
            '$\\eta$': df['eta'],
            'clip': df['clip_fraction_mean'],
            'support F1': df['selected_pair_f1_mean'],
            'true-edge sep. RMSE': df['true_realized_separator_rmse_mean'],
            'proj. RMSE': df['projection_residual_rmse_mean'],
            'outer iters': df['outer_iterations_mean'],
            'time (ms)': 1e3 * df['runtime_sec_mean'],
        }
    )
    _render_table(
        out,
        columns=list(out.columns),
        align='llrrrrrrrrr',
        caption=(
            'Experiment H: combined support uncertainty and structured mismatch using the type-cycle law on strict supergraphs. '
            'Self-consistent refinement is compared with a one-shot fit-plus-check baseline across mismatch amplitudes and oversampling regimes.'
        ),
        label='tab:supergraph_mismatch',
        stem='table_H_supergraph_mismatch',
    )




def _average_precision(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    positives = int(y_true.sum())
    if positives == 0:
        return float('nan')
    order = np.argsort(-y_score, kind='mergesort')
    y = y_true[order]
    tp = np.cumsum(y)
    fp = np.cumsum(1 - y)
    precision = tp / np.maximum(tp + fp, 1)
    return float((precision * y).sum() / positives)


def _roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    n_pos = int(y_true.sum())
    n_neg = int((1 - y_true).sum())
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    ranks = pd.Series(y_score).rank(method='average').to_numpy(dtype=float)
    rank_sum_pos = float(ranks[y_true == 1].sum())
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _binary_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum((~y_true) & y_pred))
    fn = int(np.sum(y_true & (~y_pred)))
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return float(2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0


def _sign_test_pvalue(wins: int, losses: int) -> float:
    n = int(wins) + int(losses)
    if n <= 0:
        return float('nan')
    tail = min(int(wins), int(losses))
    prob = sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n)
    return float(min(1.0, 2.0 * prob))


def table_j1_dataset_audit() -> None:
    summary_path = ROOT / 'results' / 'qtaim_main' / 'J1_dataset_audit' / 'summary.json'
    edge_path = ROOT / 'results' / 'qtaim_main' / 'J1_dataset_audit' / 'edge_level.csv'
    if not summary_path.exists():
        return
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    threshold = float(summary.get('offset_threshold_angstrom', 0.02))

    total_edges = int(summary['total_bcp_edges'])
    n_bonded = int(summary.get('bonded_bcp_edge_count', 0))
    n_nonbonded = int(summary.get('nonbonded_bcp_edge_count', 0))
    overall_median = float(summary['offset_median_angstrom'])
    bonded_median = float(summary.get('bonded_offset_median_angstrom', float('nan')))
    nonbonded_median = float(summary.get('nonbonded_offset_median_angstrom', float('nan')))
    overall_low = float(summary['low_offset_fraction'])
    bonded_low = float(summary.get('bonded_low_offset_fraction', float('nan')))
    nonbonded_low = float(summary.get('nonbonded_low_offset_fraction', float('nan')))

    if edge_path.exists():
        edge = pd.read_csv(edge_path)
        if not edge.empty:
            bonded = edge[edge['is_bonded'].astype(bool)]
            nonbonded = edge[edge['is_nonbonded'].astype(bool)]
            n_bonded = int(len(bonded))
            n_nonbonded = int(len(nonbonded))
            overall_median = float(edge['offset_angstrom'].median())
            bonded_median = float(bonded['offset_angstrom'].median()) if not bonded.empty else float('nan')
            nonbonded_median = float(nonbonded['offset_angstrom'].median()) if not nonbonded.empty else float('nan')
            overall_low = float((edge['offset_angstrom'] <= threshold).mean())
            bonded_low = float((bonded['offset_angstrom'] <= threshold).mean()) if not bonded.empty else float('nan')
            nonbonded_low = float((nonbonded['offset_angstrom'] <= threshold).mean()) if not nonbonded.empty else float('nan')

    rows = pd.DataFrame(
        {
            'Audit quantity': [
                'Molecules processed',
                'QTAIM-supported edges',
                'Bonded / nonbonded QTAIM-supported edges',
                'Molecules with at least one ring critical point',
                'Molecules with at least one cage critical point',
                'Molecules with at least one nonbonded BCP-supported edge',
                'Heteronuclear share of QTAIM-supported edges',
                'Median BCP off-axis distance (all / bonded / nonbonded)',
                rf'BCPs projecting within {threshold:.2f}~\AA{{}} of the connector (all / bonded / nonbonded)',
            ],
            'Value': [
                f"{int(summary['n_processed_rows'])}",
                f"{total_edges}",
                f"{n_bonded} / {n_nonbonded} ({100.0 * n_bonded / total_edges:.1f}\\% / {100.0 * n_nonbonded / total_edges:.2f}\\%)",
                f"{int(summary['molecules_with_rcp_count'])} ({100.0 * summary['molecules_with_rcp_fraction']:.1f}\\%)",
                f"{int(summary['molecules_with_ccp_count'])} ({100.0 * summary['molecules_with_ccp_fraction']:.1f}\\%)",
                f"{int(summary['molecules_with_nonbonded_bcp_count'])} ({100.0 * summary['molecules_with_nonbonded_bcp_fraction']:.1f}\\%)",
                f"{100.0 * summary['heteronuclear_bcp_edge_fraction']:.1f}\\%",
                fr"{overall_median:.4f} / {bonded_median:.4f} / {nonbonded_median:.3f}~\AA{{}}",
                f"{100.0 * overall_low:.1f}\\% / {100.0 * bonded_low:.1f}\\% / {100.0 * nonbonded_low:.1f}\\%",
            ],
        }
    )
    _render_table(
        rows,
        columns=list(rows.columns),
        align=r'>{\raggedright\arraybackslash}p{0.60\textwidth}r',
        caption=(
            'Experiment~J1 dataset audit. The benchmark is topologically '
            'nontrivial, but connector alignment is sharply heterogeneous '
            'between bonded and nonbonded support.'
        ),
        label='tab:j1_dataset_audit',
        stem='table_J1_dataset_audit',
        placement='t',
        resize=False,
        size_cmd=r'\footnotesize',
        tabcolsep_pt=5,
        arraystretch=1.12,
    )


def table_j23_reference_summary() -> None:
    j2_path = ROOT / 'results' / 'qtaim_main' / 'J2_true_support_ladder' / 'subset_summary.csv'
    j3_path = ROOT / 'results' / 'qtaim_main' / 'J3_candidate_recovery_refresh' / 'subset_summary.csv'
    if not j2_path.exists() or not j3_path.exists():
        return
    j2 = pd.read_csv(j2_path)
    j3 = pd.read_csv(j3_path)
    panel_a_order = ['all', 'bonded', 'nonbonded', 'heteronuclear', 'heteronuclear & offset<=0.02A']
    panel_b_order = ['all', 'bonded', 'nonbonded', 'heteronuclear']
    j2 = j2.set_index('subset')
    j3 = j3[np.isclose(j3['cutoff_angstrom'], 5.0)].set_index('subset')
    panel_a = pd.DataFrame(
        {
            'Subset': ['All', 'Bonded', 'Nonbonded', 'Heteronuclear', 'Low-offset heteronuclear'],
            'Midpoint': [j2.loc[s, 'midpoint_angstrom_rmse'] for s in panel_a_order],
            'Proatomic': [j2.loc[s, 'proatomic_angstrom_rmse'] for s in panel_a_order],
            'One-shot powerfit': [j2.loc[s, 'proatomic_powerfit_angstrom_rmse'] for s in panel_a_order],
            'Ceiling': [j2.loc[s, 'qtaim_ceiling_angstrom_rmse'] for s in panel_a_order],
        }
    )
    panel_b = pd.DataFrame(
        {
            'Subset': ['All', 'Bonded', 'Nonbonded', 'Heteronuclear'],
            'Candidate precision / F1': [
                f"{j3.loc[s, 'candidate_precision']:.3f} / {j3.loc[s, 'candidate_f1']:.3f}" for s in panel_b_order
            ],
            'Raw recovered F1': [j3.loc[s, 'recovered_f1_raw'] for s in panel_b_order],
            'Visible recovered precision / F1': [
                f"{j3.loc[s, 'recovered_precision_visible']:.3f} / {j3.loc[s, 'recovered_f1_visible']:.3f}" for s in panel_b_order
            ],
            'Visible recall': [j3.loc[s, 'recovered_recall_visible'] for s in panel_b_order],
        }
    )
    parts = [
        r'\begin{table}[H]',
        r'\caption{Reference quantitative anchors for Experiments~J2 and~J3. Panel~A reports true-support separator RMSE in \AA{} on QTAIM-supported pairs. Panel~B reports support recovery from the reference 5.0~\AA{} candidate graph, which covers all QTAIM-supported edges. Ordinary Voronoi is the midpoint-target baseline.}',
        r'\label{tab:j23_reference_summary}',
        r'\centering',
        r'\footnotesize',
        r'\setlength{\tabcolsep}{4.5pt}',
        r'\renewcommand{\arraystretch}{1.10}',
        '',
        r'\begin{tabular}{>{\raggedright\arraybackslash}p{0.19\textwidth}rrrr}',
        r'\toprule',
        r'\multicolumn{5}{l}{\textbf{Panel A: J2 true-support separator RMSE (\AA{})}} \\\\',
        r'\midrule',
        r'Subset & Midpoint & Proatomic & One-shot powerfit & Ceiling \\\\',
        r'\midrule',
    ]
    for _, row in panel_a.iterrows():
        parts.append(f"{row['Subset']} & {row['Midpoint']:.4f} & {row['Proatomic']:.4f} & {row['One-shot powerfit']:.4f} & {row['Ceiling']:.4f} \\\\")
    parts += [
        r'\bottomrule',
        r'\end{tabular}',
        '',
        r'\vspace{0.65em}',
        '',
        r'\setlength{\tabcolsep}{2.0pt}',
        r'\begin{tabular}{>{\raggedright\arraybackslash}p{0.17\textwidth}>{\raggedleft\arraybackslash}p{0.18\textwidth}>{\raggedleft\arraybackslash}p{0.12\textwidth}>{\raggedleft\arraybackslash}p{0.19\textwidth}>{\raggedleft\arraybackslash}p{0.10\textwidth}}',
        r'\toprule',
        r'\multicolumn{5}{l}{\textbf{Panel B: J3 support recovery at 5.0~\AA{} candidate cutoff}} \\\\',
        r'\midrule',
        r'Subset & \multicolumn{1}{c}{\shortstack[c]{Candidate\\precision / F1}} & \multicolumn{1}{c}{\shortstack[c]{Raw recovered\\F1}} & \multicolumn{1}{c}{\shortstack[c]{Visible\\precision / F1}} & \multicolumn{1}{c}{\shortstack[c]{Visible\\recall}} \\\\',
        r'\midrule',
    ]
    for _, row in panel_b.iterrows():
        parts.append(f"{row['Subset']} & {row['Candidate precision / F1']} & {row['Raw recovered F1']:.3f} & {row['Visible recovered precision / F1']} & {row['Visible recall']:.3f} \\\\")
    parts += [r'\bottomrule', r'\end{tabular}', r'\setlength{\tabcolsep}{4.5pt}', r'\end{table}', '']
    _write_fragment('table_J23_reference_summary', '\n'.join(parts))



def table_j4_local_validation() -> None:
    summary_path = ROOT / 'results' / 'qtaim_main' / 'J4_local_diagnostic_validation' / 'summary.json'
    if not summary_path.exists():
        return
    payload = json.loads(summary_path.read_text(encoding='utf-8'))
    rows = []
    label_map = {
        'voronoi': 'Voronoi',
        'recovered_powerfit': 'Recovered powerfit',
    }
    for row in payload.get('by_model', []):
        rows.append(
            {
                'Model': label_map.get(str(row['model']), str(row['model']).replace('_', ' ').title()),
                'Faces checked': f"{int(row['n_faces'])}",
                'Visibility mismatches': f"{int(row['n_visibility_mismatches'])}",
                'Visible faces': f"{int(row['n_visible_faces'])}",
                r'Max / mean $|\Delta c|$': rf"${_fmt_sci(float(row['max_abs_clearance_diff']))}$ / ${_fmt_sci(float(row['mean_abs_clearance_diff']))}$",
            }
        )
    df = pd.DataFrame(rows)
    _render_table(
        df,
        columns=list(df.columns),
        align=r'>{\raggedright\arraybackslash}p{0.24\textwidth}rrr>{\raggedright\arraybackslash}p{0.24\textwidth}',
        caption=(
            'Experiment~J4a local-diagnostic validation. Analytic clipped visibility '
            'and clearance are compared with tessellation-based connector-line '
            'diagnostics on the released edge-level archive; clearance errors are '
            'computed on visible faces only.'
        ),
        label='tab:j4_local_validation',
        stem='table_J4_local_validation',
        placement='H',
        resize=True,
        size_cmd=r'\footnotesize',
        tabcolsep_pt=5,
        arraystretch=1.10,
    )

def table_j4_clearance_ranking() -> None:
    edge_path = ROOT / 'results' / 'qtaim_main' / 'J4_mask_transfer_refresh' / 'edge_level.csv'
    if not edge_path.exists():
        return
    edge = pd.read_csv(edge_path)
    panel_a_rows = []
    for model, model_label in [('voronoi', 'Voronoi'), ('recovered_powerfit', 'Recovered powerfit')]:
        sub = edge[(edge['model'] == model) & edge['keep_visible'].astype(bool) & edge['is_nonbonded'].astype(bool)].copy()
        y = sub['is_qtaim_edge'].astype(int).to_numpy()
        for col, score_label, sign in [
            ('intersection_edge_min_dist', 'Connector clearance', 1.0),
            ('bond_length_angstrom', 'Short pair distance', -1.0),
            ('face_area', 'Face area', 1.0),
        ]:
            s = sign * sub[col].astype(float).to_numpy()
            panel_a_rows.append((model_label, score_label, _average_precision(y, s), _roc_auc(y, s)))
    wins = []
    for system_key, group in edge.groupby('system_key'):
        per_model = {}
        for model in ['voronoi', 'recovered_powerfit']:
            g = group[group['model'] == model].copy()
            y = g['is_qtaim_edge'].astype(bool).to_numpy()
            visible = g['keep_visible'].astype(bool).to_numpy()
            visible_thr = g['keep_visible_non_sliver'].astype(bool).to_numpy() & (
                g['intersection_edge_min_dist'].astype(float).to_numpy() >= 0.5
            )
            per_model[model] = {
                'visible_f1': _binary_f1(y, visible),
                'visible_thr_f1': _binary_f1(y, visible_thr),
            }
        wins.append(
            (
                system_key,
                per_model['recovered_powerfit']['visible_f1'] - per_model['voronoi']['visible_f1'],
                per_model['recovered_powerfit']['visible_thr_f1'] - per_model['voronoi']['visible_thr_f1'],
            )
        )
    visible_win = sum(delta > 1e-12 for _, delta, _ in wins)
    visible_loss = sum(delta < -1e-12 for _, delta, _ in wins)
    visible_tie = len(wins) - visible_win - visible_loss
    thr_win = sum(delta > 1e-12 for _, _, delta in wins)
    thr_loss = sum(delta < -1e-12 for _, _, delta in wins)
    thr_tie = len(wins) - thr_win - thr_loss
    visible_p = _sign_test_pvalue(visible_win, visible_loss)
    thr_p = _sign_test_pvalue(thr_win, thr_loss)
    parts = [
        r'\begin{table}[H]',
        "\\caption{Experiment~J4b diagnostics on visible nonbonded faces. Panel~A ranks QTAIM-supported faces above surplus visible faces within each model's realized-face archive. Panel~B gives moleculewise recovered-powerfit win counts against visible Voronoi; fixed-denominator support recovery is reported in J3.}",
        r'\label{tab:j4_clearance_ranking}',
        r'\centering',
        r'\footnotesize',
        r'\setlength{\tabcolsep}{4pt}',
        r'\renewcommand{\arraystretch}{1.10}',
        '',
        r'\begin{tabular}{>{\raggedright\arraybackslash}p{0.22\textwidth}>{\raggedright\arraybackslash}p{0.26\textwidth}rr}',
        r'\toprule',
        r'\multicolumn{4}{l}{\textbf{Panel A: visible nonbonded ranking diagnostics}} \\',
        r'\midrule',
        r'Model & Score & Average precision & ROC AUC \\',
        r'\midrule',
    ]
    for model_label, score_label, ap, auc in panel_a_rows:
        parts.append(f"{model_label} & {score_label} & {ap:.3f} & {auc:.3f} " + r"\\")
    parts += [
        r'\bottomrule',
        r'\end{tabular}',
        '',
        r'\vspace{0.65em}',
        '',
        r'\begin{tabular}{>{\raggedright\arraybackslash}p{0.42\textwidth}rrrr}',
        r'\toprule',
        r'\multicolumn{5}{l}{\textbf{Panel B: moleculewise recovered-powerfit win counts}} \\',
        r'\midrule',
        r'Comparison & Powerfit wins & Voronoi wins & Ties & $p$ \\',
        r'\midrule',
        f"Visible graph F1 & {visible_win} & {visible_loss} & {visible_tie} & {visible_p:.2g} " + r"\\",
        f"Visible graph F1 after 0.50~\\AA{{}} clearance cutoff & {thr_win} & {thr_loss} & {thr_tie} & {thr_p:.2g} " + r"\\",
        r'\bottomrule',
        r'\end{tabular}',
        r'\end{table}',
        '',
    ]
    _write_fragment('table_J4_clearance_ranking', '\n'.join(parts))

def main() -> int:
    table_j1_dataset_audit()
    table_j23_reference_summary()
    table_j4_local_validation()
    table_j4_clearance_ranking()
    table_a()
    table_b()
    table_d()
    table_e()
    table_f()
    table_g()
    table_h()
    print(f'Wrote manuscript tables to {OUTDIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
