#!/usr/bin/env python3
"""Draw two editorial figures without rerunning any numerical experiment.

Usage, from the repository::

    python scripts/plot_editorial_figures.py \
        --output-dir manuscript/figures

Dependencies: Python 3.10+, matplotlib, numpy, pandas. Frozen data default to
the repository's results/ tree. Use --results-root /path/to/results for a
copy of that tree. The source data are not regenerated or modified.

Figure C reproduces only panels (a,b) of the frozen missing-data composite.
Its source is ``results/missing_data_manuscript/runs.csv`` in powerfit-80933a1
(pyvoro2 0.6.3). Grouping, median aggregation, maximum-size profile selection,
and the 1e-16 display floor follow ``aggregate_runs``, ``_profile_rows``,
``_clip_positive``, ``_plot_rmse_profile_combined``, and
``_plot_connected_profile_combined`` in the archived
``experiments/analysis/plot_missing_data_manuscript.py``. The original top
panels have no quantile bands. This version uses conventional logarithmic
tick labels and a compact, two-panel layout. No smoothing is applied.

To regenerate Figure E alone, without reading results or rewriting C::

    python scripts/plot_editorial_figures.py \
        --figure bcp --output-dir manuscript/figures

Figure E uses an exact conceptual density in conformal coordinates. Its
bond path is a gradient path and its curved dividing surface has zero
normal density flux. A rigid rotation makes the nuclear connector
horizontal; a uniformly magnified inset resolves the small BCP projection.
The model is illustrative, not molecular data or a whole-surface fit.
See manuscript/figures/README.md for the density, domain and proof.

The source checks printed to stdout are also useful when updating the
manuscript's evidence ledger. Reproducibility concerns the plotted values
and construction; font/rendering differences may affect PDF bytes across
matplotlib installations.
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
from matplotlib.patches import ConnectionPatch, FancyArrowPatch, PathPatch, Rectangle
from matplotlib.path import Path as MplPath
from matplotlib.ticker import FixedLocator, LogFormatterMathtext, NullLocator, PercentFormatter
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results"
RUNS_PATH = "results/missing_data_manuscript/runs.csv"
SUMMARY_PATH = "results/missing_data_manuscript/manuscript_analysis/summary.csv"
METADATA_PATH = "results/missing_data_manuscript/metadata.json"
PLOT_SOURCE_PATH = "experiments/analysis/plot_missing_data_manuscript.py"
EXPECTED_RUNS_SHA256 = "da4bb4194d9e380272b258648dce43d405e0aebba934c659c1b6ac80a1e76395"
EXPECTED_SUMMARY_SHA256 = "9ac9b88c5a118d58266f315325e387eac2716efc5efddb631a7b7426aaab2a6f"
DISPLAY_FLOOR = 1e-16
GROUP_COLUMNS = ["dimension", "n_sites", "keep_fraction_requested"]
RMSE_COLUMNS = (
    "global_centered_weight_rmse_median",
    "componentwise_aligned_weight_rmse_median",
)
GLOBAL_COLOR = "#BB4B13"
COMPONENT_COLOR = "#2166AC"
CONNECTIVITY_COLOR = "#26734D"
INK = "#252525"


def load_profiles(*, results_root: Path | None = None) -> dict[int, pd.DataFrame]:
    """Reaggregate frozen runs, check the archived summary, select n=128."""
    results_root = Path(results_root) if results_root is not None else DEFAULT_RESULTS_ROOT
    runs_bytes = (results_root / Path(RUNS_PATH).relative_to("results")).read_bytes()
    summary_bytes = (results_root / Path(SUMMARY_PATH).relative_to("results")).read_bytes()
    metadata = json.loads((results_root / Path(METADATA_PATH).relative_to("results")).read_bytes())
    source_description = f"Results root: {results_root}"
    if hashlib.sha256(runs_bytes).hexdigest() != EXPECTED_RUNS_SHA256:
        raise ValueError("The run-source SHA-256 differs from the frozen Experiment C CSV")
    if hashlib.sha256(summary_bytes).hexdigest() != EXPECTED_SUMMARY_SHA256:
        raise ValueError("The summary SHA-256 differs from the frozen Experiment C CSV")

    runs = pd.read_csv(io.BytesIO(runs_bytes))
    archived_summary = pd.read_csv(io.BytesIO(summary_bytes))
    config = metadata["config"]
    package_version = metadata["provenance"]["package_versions"]["pyvoro2"]
    if package_version != "0.6.3" or len(runs) != 2470 or metadata["n_runs"] != 2470:
        raise ValueError("This figure requires the frozen 2,470-run pyvoro2 0.6.3 sweep")
    if set(runs["dimension"]) != {2, 3} or config["replicates"] != 10:
        raise ValueError("Unexpected dimensions or replicate count")
    if not runs["connected"].isin([True, False]).all():
        raise ValueError("The connected field must contain Boolean observations")

    # These three aggregations are identical to the frozen plotting script.
    summary = (
        runs.groupby(GROUP_COLUMNS, dropna=False)
        .agg(
            runs=("seed", "count"),
            connected_rate=("connected", "mean"),
            global_centered_weight_rmse_median=("global_centered_weight_rmse", "median"),
            componentwise_aligned_weight_rmse_median=("componentwise_aligned_weight_rmse", "median"),
        )
        .reset_index()
        .sort_values(GROUP_COLUMNS)
    )

    compared = summary.merge(
        archived_summary,
        on=GROUP_COLUMNS,
        suffixes=("_recomputed", "_archived"),
        validate="one_to_one",
    )
    if len(compared) != 247 or len(archived_summary) != 247:
        raise ValueError("The frozen sweep should contain 247 configuration groups")
    for column in ("runs", "connected_rate", *RMSE_COLUMNS):
        # Archival CSV serialization introduces sub-picorelative differences
        # in some decimal-valued RMSE summaries. Do not use a large absolute
        # tolerance: the values near machine precision must also agree.
        np.testing.assert_allclose(
            compared[f"{column}_recomputed"],
            compared[f"{column}_archived"],
            rtol=1e-11,
            atol=1e-30,
            err_msg=f"Reaggregation differs from the frozen summary: {column}",
        )

    profiles = {}
    for dimension in (2, 3):
        dimension_summary = summary[summary["dimension"] == dimension]
        largest_size = int(dimension_summary["n_sites"].max())
        if largest_size != 128:
            raise ValueError(f"The frozen {dimension}D maximum-size profile must have 128 sites")
        profile = dimension_summary[dimension_summary["n_sites"] == largest_size].sort_values(
            "keep_fraction_requested"
        )
        np.testing.assert_allclose(
            profile["keep_fraction_requested"], np.linspace(0.10, 1.00, 19), rtol=0, atol=1e-15
        )
        if len(profile) != 19 or not profile["runs"].eq(10).all():
            raise ValueError("Each profile must have 19 settings with 10 independent runs per setting")
        profiles[dimension] = profile

    print(source_description)
    print(f"Run source: {RUNS_PATH}")
    print(f"Run source SHA-256: {hashlib.sha256(runs_bytes).hexdigest()}")
    print(f"Summary check: {SUMMARY_PATH}; all 247 configuration groups agree")
    print(f"Plotting convention: {PLOT_SOURCE_PATH}")
    print("Selected: 380 runs; 19 settings x 10 runs x 2 dimensions; n=128")
    print("Retention: requested fraction 0.10 to 1.00 in steps of 0.05")
    print("Aggregation: median of per-run weight RMSE, then max(median, 1e-16)")
    for dimension, profile in profiles.items():
        for column in RMSE_COLUMNS:
            values = profile[column]
            print(
                f"{dimension}D {column}: range [{values.min():.17g}, {values.max():.17g}]; "
                f"{int((values < DISPLAY_FLOOR).sum())}/19 values below display floor"
            )
        connected = profile["connected_rate"].to_numpy(dtype=float)
        print(f"{dimension}D connected fractions: {', '.join(f'{value:.1f}' for value in connected)}")
    return profiles


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "DejaVu Serif"],
            "font.size": 10.6,
            "mathtext.fontset": "stix",
            "text.color": INK,
            "axes.labelcolor": INK,
            "axes.edgecolor": "#6C6C6C",
            "axes.linewidth": 0.65,
            "axes.labelsize": 11.0,
            "axes.titlesize": 10.8,
            "xtick.color": INK,
            "ytick.color": INK,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "pdf.compression": 9,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def dimension_style(dimension: int) -> dict:
    if dimension == 2:
        return {"linestyle": "-", "marker": "o"}
    return {"linestyle": (0, (2.2, 1.7)), "marker": "s", "markerfacecolor": "white"}


def save_pdf(fig: plt.Figure, path: Path, title: str, subject: str) -> None:
    fig.savefig(
        path,
        format="pdf",
        metadata={
            "Title": title,
            "Subject": subject,
            "Creator": "plot_editorial_figures.py (Matplotlib)",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    plt.close(fig)
    print(f"Wrote {path}")


def draw_identifiability(profiles: dict[int, pd.DataFrame], output: Path) -> None:
    fig, (ax_error, ax_connected) = plt.subplots(1, 2, figsize=(5.70, 2.85))
    fig.subplots_adjust(left=0.120, right=0.965, bottom=0.190, top=0.790, wspace=0.43)

    for dimension, profile in profiles.items():
        x = profile["keep_fraction_requested"].to_numpy(dtype=float)
        style = dimension_style(dimension)
        # Larger blue markers remain visible beneath smaller orange markers
        # where the two statistics are exactly equal, without jittering data.
        for column, color, marker_size, width in (
            (RMSE_COLUMNS[1], COMPONENT_COLOR, 4.0, 1.30),
            (RMSE_COLUMNS[0], GLOBAL_COLOR, 2.7, 1.25),
        ):
            ax_error.plot(
                x,
                np.maximum(profile[column].to_numpy(dtype=float), DISPLAY_FLOOR),
                color=color,
                linewidth=width,
                markersize=marker_size,
                markeredgewidth=0.85,
                markeredgecolor=color,
                **style,
            )
        ax_connected.plot(
            x,
            profile["connected_rate"],
            color=CONNECTIVITY_COLOR,
            linewidth=1.35,
            markersize=3.8,
            markeredgewidth=0.85,
            markeredgecolor=CONNECTIVITY_COLOR,
            **style,
        )

    for ax in (ax_error, ax_connected):
        ax.set_xlim(0.08, 1.02)
        ax.set_xticks([0.10, 0.25, 0.50, 0.75, 1.00])
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
        ax.set_xlabel("Requested retention", labelpad=5.0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#DDDDDD", linewidth=0.55)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", pad=3)

    ax_error.set_yscale("log")
    ax_error.set_ylim(3e-17, 2e-3)
    ax_error.yaxis.set_major_locator(FixedLocator([1e-16, 1e-12, 1e-8, 1e-4]))
    ax_error.yaxis.set_major_formatter(LogFormatterMathtext())
    ax_error.yaxis.set_minor_locator(NullLocator())
    ax_error.set_ylabel("Median weight RMSE", labelpad=5.0)
    ax_error.set_title("(a) Weight recovery", loc="left", pad=8.0)

    ax_connected.set_ylim(-0.04, 1.04)
    ax_connected.set_yticks(np.linspace(0.0, 1.0, 6))
    ax_connected.set_ylabel("Connected fraction", labelpad=5.0)
    ax_connected.set_title("(b) Connectivity", loc="left", pad=8.0)

    legend_handles = [
        Line2D([], [], color=GLOBAL_COLOR, linewidth=1.6),
        Line2D([], [], color=COMPONENT_COLOR, linewidth=1.6),
        Line2D([], [], color=INK, linewidth=1.3, markersize=3.7, **dimension_style(2)),
        Line2D([], [], color=INK, linewidth=1.3, markersize=3.7, **dimension_style(3)),
    ]
    fig.legend(
        legend_handles,
        ["Global alignment", "Oracle componentwise", "2D", "3D"],
        loc="upper center",
        bbox_to_anchor=(0.520, 0.993),
        ncol=4,
        frameon=False,
        fontsize=9.8,
        handlelength=1.8,
        handletextpad=0.45,
        columnspacing=1.0,
        borderaxespad=0.1,
    )
    save_pdf(
        fig,
        output,
        "Frozen missing-data profiles: weight identifiability and connectivity",
        "powerfit-80933a1; pyvoro2 0.6.3; 128 sites; 19 independent retention settings "
        "with ten runs each in 2D and 3D; median per-run weight RMSE, display floor 1e-16",
    )


@dataclass(frozen=True)
class ConformalBcpModel:
    """Exact illustrative density; the parameters have no molecular units.

    In coordinates w=u+iv and h, rho=exp(U(u)-beta*v^2-gamma*h^2),
    U'=-strength*(u-left)*u*(u-right), and z=g(w)=w+eta*w^2.
    The physical drawing applies only a rigid rotation and translation.
    """

    left: float = -1.5
    right: float = 0.7
    bend: float = -0.15
    off_axis: float = 0.03
    strength: float = 1.0
    beta: float = 1.0
    gamma: float = 1.0
    u_min: float = -1.65
    u_max: float = 0.85
    v_limit: float = 1.6

    @property
    def eta(self) -> complex:
        return complex(self.bend, self.off_axis)

    def g(self, w):
        return w + self.eta * w**2

    @property
    def rotation(self) -> complex:
        connector = self.g(self.right) - self.g(self.left)
        return np.conj(connector) / abs(connector)

    def physical(self, w):
        """Keep b_x=q_x=0 and put the nuclear connector at y=0."""
        connector_height = (self.rotation * self.g(self.left)).imag
        return self.rotation * self.g(w) - 1j * connector_height

    def tangent(self, w):
        """Physical derivative with respect to u; the v derivative is i times this."""
        return self.rotation * (1.0 + 2.0 * self.eta * w)

    def potential(self, u):
        return -self.strength * (
            u**4 / 4.0
            - (self.left + self.right) * u**3 / 3.0
            + self.left * self.right * u**2 / 2.0
        )

    def potential_prime(self, u):
        return -self.strength * (u - self.left) * u * (u - self.right)

    def potential_second(self, u):
        return -self.strength * (
            3.0 * u**2 - 2.0 * (self.left + self.right) * u + self.left * self.right
        )

    def planar_log_gradient(self, w):
        """Complex representation of the physical x,y gradient of log rho."""
        derivative = self.tangent(w)
        return derivative * (self.potential_prime(np.real(w)) - 2j * self.beta * np.imag(w)) / abs(derivative) ** 2

    def path(self, start: complex, stop: complex) -> MplPath:
        """Exact quadratic Bezier image of a straight coordinate segment."""
        z0 = self.physical(start)
        control = z0 + 0.5 * (stop - start) * self.tangent(start)
        z1 = self.physical(stop)
        return MplPath(
            [(z0.real, z0.imag), (control.real, control.imag), (z1.real, z1.imag)],
            [MplPath.MOVETO, MplPath.CURVE3, MplPath.CURVE3],
        )


def check_bcp_model(model: ConformalBcpModel) -> None:
    """Verify drawing identities, not a molecular experiment or model fit."""
    # For any w1,w2 in the window, g(w1)-g(w2)=(w1-w2)
    # [1+eta(w1+w2)]. Its bracket has this strictly positive real lower
    # bound. The same bound applies to Re g', proving injectivity and
    # nonvanishing derivative throughout the entire chosen rectangle.
    injection_bound = 1.0 + 2.0 * model.bend * model.u_max - 2.0 * abs(model.off_axis) * model.v_limit
    assert model.bend < 0.0 and injection_bound > 0.0
    assert model.u_min < model.left < 0.0 < model.right < model.u_max

    pi, pj, b = [model.physical(u) for u in (model.left, model.right, 0.0)]
    q = complex(b.real, 0.0)
    np.testing.assert_allclose([pi.imag, pj.imag, b.real], 0.0, rtol=0, atol=1e-15)
    np.testing.assert_allclose(((b - q) * np.conj(pj - pi)).real, 0.0, rtol=0, atol=1e-15)
    np.testing.assert_allclose(model.potential_prime(np.array([model.left, 0.0, model.right])), 0.0, rtol=0, atol=1e-15)
    assert model.potential_second(model.left) < 0.0
    assert model.potential_second(model.right) < 0.0
    assert model.potential_second(0.0) > 0.0 and model.beta > 0.0 and model.gamma > 0.0

    # Check the closed-form gradient identities at representative points;
    # the README gives the proof for every point in the coordinate window.
    v = np.linspace(-model.v_limit, model.v_limit, 41)
    w = 1j * v
    normals = model.tangent(w) / abs(model.tangent(w))
    density = np.exp(-model.beta * v**2)
    normal_flux = np.real(density * model.planar_log_gradient(w) * np.conj(normals))
    np.testing.assert_allclose(normal_flux, 0.0, rtol=0, atol=2e-15)
    u = np.linspace(model.left, model.right, 41)
    parallel_cross = np.imag(model.planar_log_gradient(u) * np.conj(model.tangent(u)))
    np.testing.assert_allclose(parallel_cross, 0.0, rtol=0, atol=2e-15)

    # Confirm that the Bezier curves represent the analytic map, including
    # their intermediate points, rather than merely joining chosen endpoints.
    for start, stop in ((model.left, model.right), (-1.35j, 1.35j)):
        vertices = model.path(start, stop).vertices
        t = np.linspace(0.0, 1.0, 9)[:, None]
        bezier = (1 - t) ** 2 * vertices[0] + 2 * (1 - t) * t * vertices[1] + t**2 * vertices[2]
        exact = model.physical(start + t[:, 0] * (stop - start))
        np.testing.assert_allclose(bezier, np.column_stack((exact.real, exact.imag)), rtol=0, atol=8e-16)

    print("BCP schematic: exact illustrative density; no molecular data or fitted surface")
    print(f"Coordinate window: u=[{model.u_min:g}, {model.u_max:g}], |v|<={model.v_limit:g}; h real")
    print(f"Injectivity and nonzero-derivative real-part bound: {injection_bound:.12g}")
    print(f"Physical sites and points: p_i={pi}, p_j={pj}, b={b}, q={q}")
    print(f"BCP off-axis distance: {abs(b - q):.12g}; connector length: {abs(pj - pi):.12g}")
    print(f"Chosen offset / connector length: {abs(b - q) / abs(pj - pi):.12g} (illustrative, not a dataset statistic)")
    print(f"Boundary-tangent / target-plane angle at b: {abs(np.degrees(np.angle(model.rotation))):.12g} degrees")
    print(f"Identity-check maximum normal density flux: {np.max(abs(normal_flux)):.3g}")
    print(f"Identity-check maximum gradient/path cross product: {np.max(abs(parallel_cross)):.3g}")


def draw_bcp_projection(output: Path) -> None:
    model = ConformalBcpModel()
    check_bcp_model(model)
    pi, pj, b = [model.physical(u) for u in (model.left, model.right, 0.0)]
    q = complex(b.real, 0.0)
    connector_color = "#858585"
    plane_style = (0, (4.0, 2.0))
    connector_style = (0, (3.0, 2.0))

    fig = plt.figure(figsize=(5.70, 3.60))
    ax = fig.add_axes([0.020, 0.205, 0.640, 0.715])
    ax.set_aspect("equal")
    ax.set_xlim(-2.09, 0.94)
    ax.set_ylim(-1.46, 1.36)
    ax.axis("off")

    def add_curves(target: plt.Axes, *, detail: bool = False) -> None:
        y_limits = (-0.065, 0.045) if detail else (-1.42, 1.32)
        target.plot([q.real, q.real], y_limits, color=GLOBAL_COLOR, linestyle=plane_style, linewidth=0.95 if detail else 1.25, zorder=2.5 if detail else 1)
        target.plot([pi.real, pj.real], [0.0, 0.0], color=connector_color, linestyle=connector_style, linewidth=1.0, zorder=1)
        target.add_patch(PathPatch(model.path(-1.35j, 1.35j), facecolor="none", edgecolor=COMPONENT_COLOR, linewidth=1.35 if detail else 1.65, zorder=2))
        target.add_patch(PathPatch(model.path(model.left, model.right), facecolor="none", edgecolor=CONNECTIVITY_COLOR, linewidth=1.6, zorder=3))

    add_curves(ax)
    for start, stop in ((-0.45, -0.80), (0.18, 0.40)):
        ax.add_patch(
            FancyArrowPatch(
                path=model.path(start, stop),
                arrowstyle="-|>",
                mutation_scale=7.5,
                color=CONNECTIVITY_COLOR,
                linewidth=1.3,
                zorder=4,
            )
        )

    ax.scatter([pi.real, pj.real], [pi.imag, pj.imag], s=26, color=INK, zorder=5)
    for point, label in ((pi, r"$p_i$"), (pj, r"$p_j$")):
        ax.annotate(label, (point.real, point.imag), xytext=(0, -10), textcoords="offset points", ha="center", va="top", fontsize=12.5)
    ax.scatter(b.real, b.imag, s=18, color=INK, zorder=7)
    ax.annotate(
        r"$b$ (BCP)",
        (b.real, b.imag),
        xytext=(-17, -19),
        textcoords="offset points",
        ha="right",
        va="top",
        fontsize=11.0,
        arrowprops={"arrowstyle": "-", "color": "#777777", "lw": 0.6, "shrinkB": 6},
    )

    # A uniform enlargement resolves the genuine small off-axis separation.
    # Main and inset both have equal x/y scale; no transverse exaggeration.
    inset = fig.add_axes([0.735, 0.370, 0.235, 0.330])
    inset.set_aspect("equal")
    inset.set_xlim(-0.045, 0.065)
    inset.set_ylim(-0.065, 0.045)
    inset.set_xticks([])
    inset.set_yticks([])
    for spine in inset.spines.values():
        spine.set_color("#BBBBBB")
        spine.set_linewidth(0.55)
    add_curves(inset, detail=True)
    inset.scatter(b.real, b.imag, s=23, color=INK, zorder=6)
    inset.scatter(q.real, q.imag, s=21, facecolor="white", edgecolor=INK, linewidth=0.85, zorder=6)
    inset.annotate(r"$b$", (b.real, b.imag), xytext=(9, -6), textcoords="offset points", ha="left", va="top", fontsize=12.0)
    inset.annotate(r"$q$", (q.real, q.imag), xytext=(9, 5), textcoords="offset points", ha="left", va="bottom", fontsize=12.0)
    corner = 0.008
    inset.plot([0.0, corner, corner], [-corner, -corner, 0.0], color="#555555", linewidth=0.65, zorder=4)
    inset.set_title("BCP detail", fontsize=10.6, pad=7.0)
    inset.text(0.5, -0.10, "uniform magnification", transform=inset.transAxes, ha="center", va="top", fontsize=9.1, color="#555555")
    ax.add_patch(Rectangle((-0.045, -0.065), 0.110, 0.110, facecolor="none", edgecolor="#A4A4A4", linewidth=0.55, zorder=6))
    for y_main, y_inset in ((0.045, 0.045), (-0.065, -0.065)):
        fig.add_artist(
            ConnectionPatch(
                xyA=(0.065, y_main), coordsA=ax.transData,
                xyB=(-0.045, y_inset), coordsB=inset.transData,
                color="#B8B8B8", linewidth=0.5, zorder=0,
            )
        )

    fig.text(0.5, 0.975, "Conceptual density schematic", ha="center", va="top", fontsize=11.0)
    fig.legend(
        [
            Line2D([], [], color=CONNECTIVITY_COLOR, linewidth=1.6),
            Line2D([], [], color=COMPONENT_COLOR, linewidth=1.65),
            Line2D([], [], color=connector_color, linewidth=1.0, linestyle=connector_style),
            Line2D([], [], color=GLOBAL_COLOR, linewidth=1.25, linestyle=plane_style),
        ],
        [
            "Gradient bond path",
            "Zero-flux boundary (2D trace)",
            "Nuclear connector",
            "Connector-normal target plane (2D trace)",
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.020),
        ncol=2,
        frameon=False,
        fontsize=9.3,
        handlelength=2.2,
        handletextpad=0.6,
        columnspacing=1.4,
        labelspacing=0.75,
    )
    save_pdf(
        fig,
        output,
        "Conceptual density: gradient bond path, zero-flux boundary and BCP projection",
        "Exact illustrative conformal-coordinate density, not molecular data; uniformly magnified "
        "detail of the small off-axis BCP projection; target plane passes through b and q, "
        "without a whole-surface fitting or realized-face claim",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, help="Frozen results tree (default: repository results/)")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "manuscript/figures", help="Directory for the two vector PDFs")
    parser.add_argument("--figure", choices=("all", "identifiability", "bcp"), default="all", help="Regenerate both figures (default), only C, or only E")
    args = parser.parse_args()

    profiles = load_profiles(results_root=args.results_root) if args.figure != "bcp" else None
    configure_style()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.figure != "bcp":
        draw_identifiability(profiles, args.output_dir / "figure_C_identifiability.pdf")
    if args.figure != "identifiability":
        draw_bcp_projection(args.output_dir / "figure_E_bcp_projection.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
