#!/usr/bin/env python3
"""Check the four current inline tables against raw committed CSV records.

This is a read-only, standard-library check, not a TeX/table generator. E/H
changes use an absolute tie tolerance of 1e-12 on unrounded paired scores.
J4b AP retains record order for ties, as in v1.0.0's table exporter.
"""

import argparse
import csv
import math
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
METHODS = ("one_shot_fit", "self_consistent_refinement")
PAIR_CONFIGURATION = ("seed", "dimension", "n_sites", "measurement", "candidate_graph", "candidate_parameter")
J2_ERRORS = ("err_midpoint_angstrom", "err_proatomic_angstrom",
             "err_proatomic_powerfit_angstrom", "err_qtaim_ceiling_angstrom")


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite value {value!r}")
    return result


def flag(row, field):
    value = row[field]
    if value not in ("True", "False"):
        raise ValueError(f"invalid {field} flag {value!r}")
    return value == "True"


def pooled_rmse(values):
    values = [number(value) for value in values]
    if not values:
        raise ValueError("empty RMSE population")
    result = math.sqrt(math.fsum(value * value for value in values) / len(values))
    return number(result)


def average_precision(labels, scores, *, descending=True):
    labels, scores = list(labels), [number(score) for score in scores]
    if len(labels) != len(scores) or not labels or not any(labels):
        raise ValueError("empty or invalid AP population (positive records required)")
    # Python's sort is stable in both directions, including reverse=True.
    order = sorted(range(len(scores)), key=scores.__getitem__, reverse=descending)
    positives, precisions = 0, []
    for rank, index in enumerate(order, 1):
        if labels[index]:
            positives += 1
            precisions.append(positives / rank)
    return math.fsum(precisions) / positives


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"empty required population: {path}")
    return rows


def edge_identity(row):
    system = row["system_key"]
    i, j = int(row["atom_i"]), int(row["atom_j"])
    if not system or i < 1 or j < 1 or i == j:
        raise ValueError(f"invalid edge identity: {(system, i, j)}")
    return system, min(i, j), max(i, j)


def unique_edges(rows):
    result = {}
    for row in rows:
        key = edge_identity(row)
        if key in result:
            raise ValueError(f"duplicate edge identity {key}")
        result[key] = row
    if not result:
        raise ValueError("empty required edge population")
    return result


def refinement_metrics(rows, study):
    extra = (("extra_row_model", "true_row_noise_sigma", "extra_row_noise_sigma")
             if study == "E" else ("law_family", "eta", "clip_fraction"))
    pairs = {}
    for row in rows:
        key = tuple(row[field] for field in PAIR_CONFIGURATION + extra)
        if not all(key):
            raise ValueError(f"empty pair configuration {key}")
        method = row["method"]
        if method not in METHODS:
            raise ValueError(f"unexpected method {method!r}")
        if method in pairs.setdefault(key, {}):
            raise ValueError(f"duplicate method pair {key}: {method}")
        pairs[key][method] = row
    if not pairs:
        raise ValueError("empty paired population")
    for key, pair in pairs.items():
        if set(pair) != set(METHODS):
            raise ValueError(f"incomplete method pair {key}")
    metrics = {}
    for label, field, direction in (("RMSE", "true_realized_separator_rmse", -1),
                                    ("F1", "selected_pair_f1", 1)):
        first = [number(pair[METHODS[0]][field]) for pair in pairs.values()]
        refined = [number(pair[METHODS[1]][field]) for pair in pairs.values()]
        changes = [direction * (b - a) for a, b in zip(first, refined)]
        metrics[label] = [math.fsum(first) / len(first), math.fsum(refined) / len(refined),
                          sum(change > 1e-12 for change in changes),
                          sum(abs(change) <= 1e-12 for change in changes),
                          sum(change < -1e-12 for change in changes)]
    return metrics


def j2_metrics(rows):
    unique_edges(rows)
    bonded, nonbonded = [], []
    for row in rows:
        b, n = flag(row, "is_bonded"), flag(row, "is_nonbonded")
        if b == n:
            raise ValueError("bonded/nonbonded populations must partition J2")
        (bonded if b else nonbonded).append(row)
    return {label: [pooled_rmse(row[field] for row in subset) for field in J2_ERRORS]
            for label, subset in (("All", rows), ("Bonded", bonded), ("Nonbonded", nonbonded))}


def j3_metrics(candidates, selected, reference):
    candidate_map, selected_map, reference_map = map(unique_edges, (candidates, selected, reference))
    reference_ids = set(reference_map)
    systems = {key[0] for key in reference_ids}
    if any({key[0] for key in edges} != systems for edges in (candidate_map, selected_map)):
        raise ValueError("J3 system population differs from reference")
    candidate_positive = {key for key, row in candidate_map.items() if flag(row, "is_qtaim_edge")}
    selected_positive = {key for key, row in selected_map.items() if flag(row, "is_qtaim_edge")}
    if candidate_positive != reference_ids or selected_positive != reference_ids:
        raise ValueError("J3 reference identity mismatch in candidate/selected populations")
    visible = {key for key, row in selected_map.items() if flag(row, "intersection_inside")}
    if not visible:
        raise ValueError("empty J3 visible population")
    for key, row in reference_map.items():
        actual = selected_map[key]
        if flag(row, "intersection_inside") != flag(actual, "intersection_inside"):
            raise ValueError(f"J3 reference visibility mismatch: {key}")
        if number(row["err_recovered_angstrom"]) != number(actual["err_recovered_angstrom"]):
            raise ValueError(f"J3 reference error mismatch: {key}")
    true_positive = len(visible & reference_ids)
    return [len(candidates), len(selected), len(visible),
            pooled_rmse(row["err_recovered_angstrom"] for row in reference),
            true_positive / len(visible), true_positive / len(reference)]


def literal_rows(path, label):
    """Read only the current literal rows between midrule and bottomrule."""
    text = path.read_text(encoding="utf-8")
    marker = rf"\label{{{label}}}"
    if text.count(marker) != 1:
        raise ValueError(f"expected exactly one {marker}")
    tail = text.split(marker, 1)[1]
    match = re.search(r"\\begin\{tabular\}.*?\\midrule(.*?)\\bottomrule.*?\\end\{tabular\}", tail, re.S)
    if match is None:
        raise ValueError("missing current literal tabular block")
    body = re.sub(r"\\cmidrule(?:\([^)]*\))?\{[^}]*\}", "", match[1])
    return [[cell.strip() for cell in row.strip().split("&")]
            for row in body.split(r"\\") if row.strip()]


def compare_table(path, label, expected_rows, columns, decimals):
    rows = literal_rows(path, label)
    if len(rows) != len(expected_rows):
        raise ValueError(f"expected {len(expected_rows)} rows, found {len(rows)}")
    errors = []
    previous_name = ""
    for row, expected in zip(rows, expected_rows):
        previous_name = expected[0] or previous_name
        row_name = " / ".join([previous_name, *[value for value in expected[1:] if isinstance(value, str)]])
        if len(row) != len(columns):
            raise ValueError(f"row {row_name}: expected {len(columns)} columns, found {len(row)}")
        for cell, value, column, places in zip(row, expected, columns, decimals):
            if places is None:
                matches, wanted = cell == value, value
            else:
                wanted = str(value) if places == 0 else f"{value:.{places}f}"
                cleaned = cell.replace(",", "")
                # Compare printed precision rather than accepting an extra rounding step.
                matches = cleaned == wanted
            if not matches:
                errors.append(f"{label}: row {row_name}, column {column}: printed {cell!r}, expected {wanted}")
    return errors


def check_tables(results_root=REPO_ROOT / "results", manuscript_dir=REPO_ROOT / "manuscript"):
    """Return descriptive discrepancies, without writing or importing scientific code."""
    results_root, manuscript_dir = Path(results_root), Path(manuscript_dir)
    errors = []
    molecular = results_root / "qtaim_main"
    label = "tab:refinement-paired"
    try:
        e = read_csv(results_root / "active_set/runs.csv")
        h = read_csv(results_root / "supergraph_mismatch/runs.csv")
        # Validate all pairs, including H's excluded eta=0 rows.
        refinement_metrics(e, "E")
        refinement_metrics(h, "H")
        if len(e) != 40 or len(h) != 192:
            raise ValueError(f"E/H population counts: expected 40/192 rows, found {len(e)}/{len(h)}")
        eta_counts = {eta: sum(number(row["eta"]) == eta for row in h) for eta in (0, 0.1, 0.2, 0.4)}
        if any(count != 48 for count in eta_counts.values()) or sum(eta_counts.values()) != len(h):
            raise ValueError(f"H eta population counts: expected 48 per setting, found {eta_counts}")
        h = [row for row in h if number(row["eta"]) > 0]
        em, hm = refinement_metrics(e, "E"), refinement_metrics(h, "H")
        expected = [["E (20)", "RMSE", *em["RMSE"]], ["", "F1", *em["F1"]],
                    [r"H ($\eta>0$, 72)", "RMSE", *hm["RMSE"]], ["", "F1", *hm["F1"]]]
        errors += compare_table(manuscript_dir / "sections/06_experiments.tex", label, expected,
                                ["Study", "Score", "One pass", "Refined", "Better", "Tied", "Worse"],
                                [None, None, 5, 5, 0, 0, 0])
    except (OSError, ValueError, KeyError, OverflowError) as exc:
        errors.append(f"{label}: {exc}")

    label = "tab:molecular-fits"
    j2_ids = None
    try:
        rows = read_csv(molecular / "J2_true_support_ladder/edge_level.csv")
        metrics = j2_metrics(rows)
        populations = (len(rows), sum(flag(row, "is_bonded") for row in rows), sum(flag(row, "is_nonbonded") for row in rows))
        if populations != (3975, 3703, 272) or len({row["system_key"] for row in rows}) != 100:
            raise ValueError(f"J2 population: expected 3975/3703/272 pairs and 100 systems, found {populations}")
        j2_ids = set(unique_edges(rows))
        errors += compare_table(manuscript_dir / "sections/07_molecular.tex", label,
                                [[subset, *values] for subset, values in metrics.items()],
                                ["Subset", "Midpoint", "Proatomic", "Proatomic fit", "QTAIM-target fit"], [None, 4, 4, 4, 4])
    except (OSError, ValueError, KeyError, OverflowError) as exc:
        errors.append(f"{label}: {exc}")

    label = "tab:molecular-clearance-ranking"
    try:
        rows = read_csv(molecular / "J4_mask_transfer_refresh/edge_level.csv")
        known_systems = {key[0] for key in j2_ids} if j2_ids is not None else None
        if {row["model"] for row in rows} != {"voronoi", "recovered_powerfit"}:
            raise ValueError("J4b missing/unexpected model population")
        expected = []
        for model, name, count, positives in (("voronoi", "Voronoi", 2269, 258), ("recovered_powerfit", "Power fit", 1998, 270)):
            model_rows = [row for row in rows if row["model"] == model]
            unique_edges(model_rows)
            eligible = [row for row in model_rows if flag(row, "keep_visible") and flag(row, "is_nonbonded")]
            labels = [flag(row, "is_qtaim_edge") for row in eligible]
            if (len(eligible), sum(labels)) != (count, positives):
                raise ValueError(f"{model} population: expected {count}/{positives} eligible/positive, found {len(eligible)}/{sum(labels)}")
            for row in eligible:
                if known_systems is not None and row["system_key"] not in known_systems:
                    raise ValueError(f"{model} unknown system in eligible population: {row['system_key']}")
                if not flag(row, "intersection_inside") or flag(row, "is_bonded"):
                    raise ValueError(f"{model} invalid visible nonbonded population")
                if j2_ids is not None and flag(row, "is_qtaim_edge") != (edge_identity(row) in j2_ids):
                    raise ValueError(f"{model} reference identity mismatch: {edge_identity(row)}")
            aps = [average_precision(labels, [row[field] for row in eligible], descending=descending)
                   for field, descending in (("intersection_edge_min_dist", True), ("bond_length_angstrom", False), ("face_area", True))]
            expected.append([name, len(eligible), sum(labels), *aps])
        errors += compare_table(manuscript_dir / "sections/07_molecular.tex", label, expected,
                                ["Model", "Visible pairs", "QTAIM+", "Clearance AP", "Short-dist. AP", "Area AP"], [None, 0, 0, 3, 3, 3])
    except (OSError, ValueError, KeyError, OverflowError) as exc:
        errors.append(f"{label}: {exc}")

    label = "tab:molecular-candidates"
    try:
        directory = molecular / "J3_candidate_recovery_refresh"
        populations = [read_csv(directory / name) for name in ("candidate_edge_level.csv", "selected_edge_level.csv", "qtaim_edge_level.csv")]
        for rows in populations:
            if {number(row["cutoff_angstrom"]) for row in rows} != {4.0, 4.5, 5.0}:
                raise ValueError("J3 missing/unexpected cutoff population")
        expected = []
        for cutoff in (4.0, 4.5, 5.0):
            candidates, selected, reference = [[row for row in rows if number(row["cutoff_angstrom"]) == cutoff] for rows in populations]
            reference_ids = set(unique_edges(reference))
            if len(reference_ids) != 3975 or len({row["system_key"] for row in reference}) != 100:
                raise ValueError(f"J3 cutoff {cutoff}: expected 3975 reference pairs across 100 systems")
            if j2_ids is not None and reference_ids != j2_ids:
                raise ValueError(f"J3 cutoff {cutoff}: reference identity differs from J2")
            expected.append([f"{cutoff:.1f}", *j3_metrics(candidates, selected, reference)])
        errors += compare_table(manuscript_dir / "appendices/appendix_e.tex", label, expected,
                                ["Cutoff", "Candidates", "Realized", "Visible", "RMSE", "Visible precision", "Visible recall"], [None, 0, 0, 0, 4, 4, 4])
    except (OSError, ValueError, KeyError, OverflowError) as exc:
        errors.append(f"{label}: {exc}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=REPO_ROOT / "results")
    parser.add_argument("--manuscript-dir", type=Path, default=REPO_ROOT / "manuscript")
    args = parser.parse_args()
    errors = check_tables(args.results_root, args.manuscript_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("All four inline manuscript tables agree with raw CSV evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
