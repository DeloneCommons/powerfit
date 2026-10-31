#!/usr/bin/env python3
"""Read-only completeness checks for A--H and the committed-data J replay.

This checks populations and recorded fit/diagnostic outcomes, not scientific
recomputation or frozen-file hashes. It writes nothing and uses only the standard
library. J systems are compared to the committed systems_final.csv manifest.
"""

import argparse
import csv
import json
import math
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data/qtaim_main/systems_final.csv"
SYNTHETIC_COUNTS = {
    "exact_recovery": 16, "noise_robustness": 144, "missing_data": 30,
    "missing_data_manuscript": 2470, "infeasible": 30, "active_set": 40,
    "periodic": 132, "model_mismatch": 2280, "supergraph_mismatch": 192,
}
J4_RUNS = (
    "J4_mask_transfer_refresh", "J4_mask_transfer_margin3_refresh",
    "J4_mask_transfer_margin7_refresh", "J4_mask_transfer_margin10_refresh",
)
MODELS = ("voronoi", "recovered_powerfit")
CUTOFFS = (4.0, 4.5, 5.0)
MARGIN_LABELS = ("3A", "5A", "7A", "10A")
# Generous absolute floating-point comparison tolerance in Angstrom.
CLEARANCE_TOLERANCE = 1e-10


def _csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json(path):
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: expected a JSON object")
    return value


def _count(value, expected, field):
    if type(value) is not int or value != expected:
        raise ValueError(f"{field}: expected {expected}, got {value!r}")


def _identities(rows, fields, expected):
    actual = [tuple(row[field] for field in fields) for row in rows]
    if any(any(not value for value in identity) for identity in actual):
        raise ValueError(f"empty identity in {fields}")
    observed = set(actual)
    if len(actual) != len(observed) or observed != expected:
        raise ValueError(
            f"incomplete/duplicate identities {fields}: expected {len(expected)}, "
            f"got {len(actual)} rows/{len(observed)} unique; "
            f"missing {len(expected - observed)}, unexpected {len(observed - expected)}"
        )


def _fit_statuses(rows, fields):
    for index, row in enumerate(rows, 2):
        for field in fields:
            if row[field] != "optimal":
                raise ValueError(f"row {index} {field}: expected optimal, got {row[field]!r}")
    # 'converged' can describe the outer refinement, whose cycle_detected
    # termination is a legitimate experimental outcome, particularly in H.


def _synthetic(directory, expected):
    metadata = _json(directory / "metadata.json")
    _count(metadata.get("n_runs"), expected, "metadata n_runs")
    rows = _csv(directory / "runs.csv")
    _count(len(rows), expected, "runs.csv row count")
    if directory.name != "infeasible":
        _fit_statuses(rows, ("status",))


def _molecular(directory, systems):
    summary = _json(directory / "summary.json")
    for field, expected in (("n_manifest_rows", 100), ("n_processed_rows", 100),
                            ("n_skipped_rows", 0)):
        _count(summary.get(field), expected, field)
    # pandas writes a blank line for an empty DataFrame; this is legitimate
    # only with the explicit zero skipped count checked above.
    if _csv(directory / "skipped_rows.csv"):
        raise ValueError("skipped_rows.csv contains skipped molecular inputs")
    rows = _csv(directory / "molecule_level.csv")
    if directory.name.startswith("J3"):
        if summary.get("cutoffs_angstrom") != list(CUTOFFS):
            raise ValueError(f"cutoffs_angstrom: expected {list(CUTOFFS)}")
        _count(summary.get("n_cutoff_runs"), 300, "n_cutoff_runs")
        # Canonical numeric spelling makes 4 and 4.0 the same identity.
        rows = [dict(row, cutoff_angstrom=str(float(row["cutoff_angstrom"]))) for row in rows]
        expected = {(key, str(cutoff)) for key in systems for cutoff in CUTOFFS}
        _identities(rows, ("system_key", "cutoff_angstrom"), expected)
        _fit_statuses(rows, ("fit_status",))
    elif directory.name.startswith("J4"):
        _identities(rows, ("system_key", "model"),
                    {(key, model) for key in systems for model in MODELS})
    else:
        _identities(rows, ("system_key",), {(key,) for key in systems})
        if directory.name.startswith("J2"):
            _fit_statuses(rows, ("fit_status_proatomic_powerfit", "fit_status_qtaim_ceiling"))


def _diagnostic_values(row):
    values = {}
    for field in ("n_faces", "n_visible_faces", "n_visibility_mismatches", "max_abs_clearance_diff"):
        value = float(row[field])
        if not math.isfinite(value):
            raise ValueError(f"{field}: expected a finite value, got {value!r}")
        if field != "max_abs_clearance_diff" and (value < 0 or not value.is_integer()):
            raise ValueError(f"{field}: expected a nonnegative integer")
        values[field] = value
    if values["n_faces"] <= 0 or not 0 < values["n_visible_faces"] <= values["n_faces"]:
        raise ValueError("missing or invalid face/visible-face population")
    if values["n_visibility_mismatches"] != 0:
        raise ValueError("n_visibility_mismatches: expected zero")
    if not 0 <= values["max_abs_clearance_diff"] <= CLEARANCE_TOLERANCE:
        raise ValueError(f"max_abs_clearance_diff: expected 0 <= difference <= {CLEARANCE_TOLERANCE} Angstrom")
    return values


def _local_diagnostics(directory):
    summary = _json(directory / "summary.json")
    _count(summary.get("n_models"), 2, "n_models")
    _count(summary.get("total_visibility_mismatches"), 0, "total_visibility_mismatches")
    models = summary["by_model"]
    csv_rows = _csv(directory / "summary.csv")
    expected = {(model,) for model in MODELS}
    _identities(models, ("model",), expected)
    _identities(csv_rows, ("model",), expected)
    json_values = {row["model"]: _diagnostic_values(row) for row in models}
    csv_values = {row["model"]: _diagnostic_values(row) for row in csv_rows}
    if json_values != csv_values:
        raise ValueError("summary.csv diagnostics disagree with summary.json by_model")
    overall = _diagnostic_values({
        "n_faces": summary["total_faces"],
        "n_visible_faces": summary["total_visible_faces"],
        "n_visibility_mismatches": summary["total_visibility_mismatches"],
        "max_abs_clearance_diff": summary["max_abs_clearance_diff"],
    })
    for field in ("n_faces", "n_visible_faces", "n_visibility_mismatches"):
        if overall[field] != sum(values[field] for values in json_values.values()):
            raise ValueError(f"{field}: total disagrees with model populations")
    if overall["max_abs_clearance_diff"] != max(v["max_abs_clearance_diff"] for v in json_values.values()):
        raise ValueError("max_abs_clearance_diff: total disagrees with model diagnostics")


def _margin_summary(directory):
    summary = _json(directory / "summary.json")
    _count(summary.get("n_runs"), 4, "n_runs")
    if summary.get("labels") != list(MARGIN_LABELS):
        raise ValueError(f"labels: expected {list(MARGIN_LABELS)}")
    rows = _csv(directory / "summary.csv")
    expected = {(label, model, subset) for label in MARGIN_LABELS for model in MODELS
                for subset in ("all", "nonbonded", "visible_nonbonded_ranking")}
    _identities(rows, ("label", "model", "subset"), expected)


def check_results(results_root):
    """Return descriptive errors for missing/incomplete recorded replay results."""
    root = Path(results_root)
    errors = []

    def check(path, function, *arguments):
        try:
            function(path, *arguments)
        except (OSError, ValueError, TypeError, KeyError, csv.Error) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")

    for name, count in SYNTHETIC_COUNTS.items():
        check(root / name, _synthetic, count)
    try:
        manifest = _csv(MANIFEST_PATH)
        systems = {row["system_key"] for row in manifest}
        if len(manifest) != 100 or len(systems) != 100 or "" in systems:
            raise ValueError("expected 100 unique nonempty system_key values")
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        errors.append(f"systems_final.csv manifest: {exc}")
        return errors
    molecular = root / "qtaim_main"
    for name in ("J1_dataset_audit", "J2_true_support_ladder", "J3_candidate_recovery_refresh", *J4_RUNS):
        check(molecular / name, _molecular, systems)
    check(molecular / "J4_local_diagnostic_validation", _local_diagnostics)
    check(molecular / "J4_box_margin_summary_refresh", _margin_summary)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=REPO_ROOT / "results")
    args = parser.parse_args(argv)
    errors = check_results(args.results_root)
    if errors:
        print("Rerun completeness checks failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Rerun completeness checks passed: A--H and committed-data J replay populations, fit statuses, and local diagnostics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
