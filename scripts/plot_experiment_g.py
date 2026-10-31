#!/usr/bin/env python3
"""Draw the integrated Experiment G distribution figure from frozen results.

By default read the repository's frozen results/ tree. Use --results-root
/path/to/results for a copy. No experiment, fitting call or solver is run.
Each difference pairs the fit with its midpoint baseline on the same instance.
Instances at different eta settings are independent, so no trajectories are
drawn. The extra exact_control population is not pooled with the two laws'
own eta=0 populations. All 2,160 records for these laws are retained.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results"
RUNS_PATH = "results/model_mismatch/runs.csv"
METADATA_PATH = "results/model_mismatch/metadata.json"
EXPECTED_RUNS_SHA256 = "8af39990eb3f1931a79f08099ddfea3b42974121ebd0c25bf71a3b0101af0a5c"
ETAS = (0.0, 0.03, 0.06, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50)
LAWS = ("type_cycle", "local_context")
INK, BLUE, ORANGE, GREY = "#252525", "#2166AC", "#BB4B13", "#828282"


@dataclass(frozen=True)
class FigureData:
    runs: pd.DataFrame
    source_sha256: str


def load_runs(*, results_root: Path | None = None) -> FigureData:
    results_root = Path(results_root) if results_root is not None else DEFAULT_RESULTS_ROOT
    source = (results_root / Path(RUNS_PATH).relative_to("results")).read_bytes()
    metadata = json.loads((results_root / Path(METADATA_PATH).relative_to("results")).read_bytes())
    source_description = f"Results root: {results_root}"
    source_sha256 = hashlib.sha256(source).hexdigest()
    if source_sha256 != EXPECTED_RUNS_SHA256:
        raise ValueError("The run-source SHA-256 differs from the frozen Experiment G CSV")
    if (metadata["provenance"]["package_versions"]["pyvoro2"] != "0.6.3"
            or metadata["n_runs"] != 2280 or metadata["preset"] != "archived"
            or metadata["config"]["measurement"] != "fraction"):
        raise ValueError("This figure requires the archived fraction-coordinate results")
    runs = pd.read_csv(io.BytesIO(source), dtype={"seed": "string"})
    identifiers = ["seed", "geometry_family", "dimension", "n_sites", "law_family", "eta"]
    metrics = ["measurement_rmse", "midpoint_measurement_rmse",
               "realized_graph_f1", "midpoint_realized_graph_f1", "clip_fraction",
               "measurement_rmse_gain_over_midpoint"]
    if missing := set(identifiers + metrics).difference(runs.columns):
        raise ValueError(f"Missing fields: {sorted(missing)}")
    if len(runs) != 2280 or runs[identifiers].isna().any().any():
        raise ValueError("Expected 2,280 records with complete identifiers")
    if not runs["seed"].str.fullmatch(r"\d+").all() or runs["seed"].nunique() != 2280:
        raise ValueError("Expected unique exact decimal seed strings")
    if not np.isfinite(runs[metrics].to_numpy(dtype=float)).all():
        raise ValueError("Every archived metric must be finite")
    if runs["law_family"].value_counts().to_dict() != {
            "type_cycle": 1080, "local_context": 1080, "exact_control": 120}:
        raise ValueError("Unexpected law populations")
    if not runs["status"].eq("optimal").all() or not runs["solver"].eq("analytic").all():
        raise ValueError("Unexpected archived fit status or solver")

    # The sole scientific selection: retain both mismatch laws, at all eta.
    selected = runs.loc[runs["law_family"].isin(LAWS)].copy()
    sizes = {2: {32, 64, 128}, 3: {24, 48, 96}}
    for dim, expected in sizes.items():
        if set(selected.loc[selected["dimension"].eq(dim), "n_sites"]) != expected:
            raise ValueError("Unexpected size population")
    if set(selected["geometry_family"]) != {"hard_core_random", "perturbed_lattice"}:
        raise ValueError("Unexpected geometry families")
    if len(selected) != 2160 or set(selected["eta"]) != set(ETAS):
        raise ValueError("Expected all 2,160 law records at all nine eta settings")
    groups = selected.groupby(["law_family", "dimension", "eta"]).size()
    cells = selected.groupby(["law_family", "dimension", "eta", "geometry_family", "n_sites"]).size()
    if len(groups) != 36 or not groups.eq(60).all() or len(cells) != 216 or not cells.eq(10).all():
        raise ValueError("Each law/dimension/eta must contain six configurations, ten runs each")
    selected["rmse_reduction"] = selected["midpoint_measurement_rmse"] - selected["measurement_rmse"]
    selected["f1_change"] = selected["realized_graph_f1"] - selected["midpoint_realized_graph_f1"]
    if not selected["midpoint_measurement_rmse"].gt(0).all():
        raise ValueError("Relative improvement requires a positive midpoint RMSE")
    selected["relative_rmse_reduction"] = 100 * selected["rmse_reduction"] / selected["midpoint_measurement_rmse"]
    np.testing.assert_allclose(
        selected["rmse_reduction"] / selected["midpoint_measurement_rmse"],
        selected["measurement_rmse_gain_over_midpoint"], rtol=0, atol=5e-14,
    )
    if not selected["rmse_reduction"].gt(0).all():
        raise ValueError("Expected lower target RMSE for every fitted instance")
    reference = selected.loc[selected["eta"].eq(0.20), "f1_change"]
    if (int(reference.lt(0).sum()), int(reference.eq(0).sum()), int(reference.gt(0).sum())) != (193, 11, 36):
        raise ValueError("Unexpected eta=0.20 graph-F1 comparison")
    selected = selected.sort_values(identifiers).reset_index(drop=True)
    print(f"{source_description}\nRun source: {RUNS_PATH}\nSource SHA-256: {source_sha256}")
    print("Selection: 2,160 records; 60 runs per law/dimension/eta; no status filtering")
    print("All 2,160 paired fits have lower imposed-target RMSE than their midpoint baseline")
    print("At eta=0.20: graph F1 decreases in 193, ties in 11, increases in 36 of 240 runs")
    print("Type-cycle mean clipped fraction at eta=0.50: " + str(
        selected.loc[selected["law_family"].eq("type_cycle") & selected["eta"].eq(0.50), "clip_fraction"].mean()))
    return FigureData(selected, source_sha256)


def configure_style() -> None:
    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"],
        "font.size": 10.0, "mathtext.fontset": "stix", "text.color": INK,
        "axes.labelcolor": INK, "axes.edgecolor": GREY, "axes.linewidth": 0.65,
        "axes.labelsize": 10.0, "axes.titlesize": 10.8,
        "xtick.color": INK, "ytick.color": INK, "xtick.labelsize": 8.7, "ytick.labelsize": 9.5,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 3.0, "ytick.major.size": 3.0,
        "pdf.fonttype": 42, "ps.fonttype": 42, "pdf.compression": 9,
        "svg.fonttype": "path", "svg.hashsalt": "powerfit-experiment-G-candidate-2026-10-30",
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })


def draw_figure(data: FigureData, output_dir: Path) -> tuple[Path, Path]:
    configure_style()
    fig, axes = plt.subplots(2, 2, figsize=(5.70, 5.10), sharex=True, sharey="row")
    fig.subplots_adjust(left=0.150, right=0.984, bottom=0.128, top=0.850, wspace=0.12, hspace=0.25)
    rng = np.random.default_rng(20261030)
    # Jitter only horizontal positions. Reuse each run's jitter for both metrics.
    # Do not move exact zero F1 changes off the equality line.
    for col, law in enumerate(LAWS):
        for eta_index, eta in enumerate(ETAS):
            for dim, color, marker, dodge in ((2, BLUE, "o", -0.18), (3, ORANGE, "s", 0.18)):
                group = data.runs.loc[data.runs["law_family"].eq(law)
                                      & data.runs["eta"].eq(eta)
                                      & data.runs["dimension"].eq(dim)].sort_values("seed")
                center = eta_index + dodge
                x = center + rng.uniform(-0.135, 0.135, len(group))
                for row, metric in enumerate(("relative_rmse_reduction", "f1_change")):
                    ax = axes[row, col]
                    values = group[metric].to_numpy(dtype=float)
                    lo, hi = np.quantile(values, [0.25, 0.75], method="linear")
                    ax.scatter(x, values, s=3.0, c=color, marker=marker, alpha=0.25,
                               linewidths=0, zorder=2)
                    ax.plot([center, center], [lo, hi], color=color, lw=2.1,
                            solid_capstyle="butt", zorder=3)
                    ax.plot(center, values.mean(), marker=marker, markersize=4.0,
                            markerfacecolor="white", markeredgecolor=color,
                            markeredgewidth=0.9, linestyle="none", zorder=4)
        for row in range(2):
            ax = axes[row, col]
            ax.axhline(0, color=GREY, linewidth=0.8, zorder=1)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_xlim(-0.55, 8.55)
            ax.set_xticks(range(len(ETAS)), ["0", ".03", ".06", ".10", ".15", ".20", ".30", ".40", ".50"])
            ax.grid(axis="y", color="#E7E7E7", linewidth=0.45)
            ax.set_axisbelow(True)
            ax.tick_params(axis="y", pad=3)
            if col == 1:
                ax.tick_params(axis="y", length=0)
                ax.spines["left"].set_visible(False)
        law_title = ("Type-cycle", "Local-context")[col]
        axes[0, col].set_title(f"({chr(97 + col)}) {law_title}", loc="left", pad=7)
        axes[1, col].set_title(f"({chr(99 + col)}) {law_title}", loc="left", pad=7)
    axes[0, 0].set(ylim=(-4, 104), yticks=[0, 25, 50, 75, 100],
                   ylabel="Target RMSE reduction (%)\nrelative to midpoint")
    axes[1, 0].set(ylim=(-0.165, 0.069), yticks=[-0.15, -0.10, -0.05, 0, 0.05],
                   ylabel="Realized-graph F1 change\n(fit − midpoint)")
    axes[0, 0].yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    axes[1, 0].yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    fig.supxlabel(r"Nominal perturbation amplitude $\eta$", x=0.565, y=0.050, fontsize=10.5)
    handles = [Line2D([], [], marker=marker, color=color, markerfacecolor="white",
                      markeredgewidth=0.9, markersize=4.5, linestyle="none", label=label)
               for label, color, marker in (("2D", BLUE, "o"), ("3D", ORANGE, "s"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.565, 1.0),
               ncol=2, frameon=False, fontsize=10.0, handletextpad=0.3, columnspacing=1.5)
    fig.text(0.565, 0.927, "Small points: runs; open markers: means; bars: middle 50%",
             ha="center", va="center", fontsize=9.0)
    fig.text(0.565, 0.014, "Positive values favor the fit in both rows", ha="center", fontsize=9.0)

    # No limit or display convention may suppress an inconvenient observation.
    for row, metric in enumerate(("relative_rmse_reduction", "f1_change")):
        low, high = axes[row, 0].get_ylim()
        if not data.runs[metric].between(low, high, inclusive="neither").all():
            raise ValueError(f"A {metric} value would lie on or outside the display limits")

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "figure_G_mismatch.pdf"
    svg_path = output_dir / "figure_G_mismatch.svg"
    title = "Experiment G: fitting and adjacency changes across perturbation amplitude"
    provenance = (f"Candidate; powerfit-80933a1; pyvoro2 0.6.3; {RUNS_PATH}; "
                  f"source SHA-256 {data.source_sha256}; 2,160 records; 60 per law/dimension/eta. "
                  "Paired fit-minus-baseline comparisons; independent instances across eta. "
                  "Top: mean of per-run percentage RMSE reductions, 100*(midpoint-fit)/midpoint. "
                  "Bottom: whole-realized-graph F1 fit minus midpoint. All data shown; "
                  "arithmetic means and central 50% intervals; no experiments rerun.")
    fig.savefig(pdf_path, metadata={"Title": title, "Subject": provenance,
                "Creator": "plot_experiment_g.py (Matplotlib)", "CreationDate": None, "ModDate": None})
    fig.savefig(svg_path, metadata={"Title": title, "Description": provenance,
                "Creator": "plot_experiment_g.py (Matplotlib)", "Date": None})
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
    plt.close(fig)
    print(f"Wrote {pdf_path}\nWrote {svg_path}")
    return pdf_path, svg_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, help="Frozen results tree (default: repository results/)")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "manuscript/figures")
    args = parser.parse_args()
    draw_figure(load_runs(results_root=args.results_root), args.output_dir)


if __name__ == "__main__":
    main()
