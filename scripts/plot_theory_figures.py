#!/usr/bin/env python3
"""Reproduce deterministic teaching figures for powerfit Sections 2--5.

No experiment, optimization benchmark, or molecular calculation is run.
PDFs are the LaTeX assets; matching SVGs are editable vector sources.
See manuscript/figures/README.md for the exact constructions.
"""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath
import numpy as np


INK = "#252525"
BLUE = "#2166AC"
ORANGE = "#BB4B13"
GREY = "#828282"
CELL_COLORS = ("#E8F0F8", "#FBEEE5", "#F3F3F3", "#F3F3F3")
FOUR_SITES = np.array([[0., 0.], [2., 0.], [1., 1.], [1., -1.]])
FACE_WEIGHTS = (
    np.array([0., 0., 1., 1.]),
    np.array([0., 0., 1., -3.]),
    np.array([0., 0., -1., -1.]),
)
FACE_WINDOW = (-0.6, 2.6, -1.9, 1.4)


def configure_style() -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["STIXGeneral", "DejaVu Serif"],
        "font.size": 10.6,
        "mathtext.fontset": "stix",
        "text.color": INK,
        "axes.labelcolor": INK,
        "axes.edgecolor": GREY,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "pdf.compression": 9,
        "svg.fonttype": "path",
        "svg.hashsalt": "powerfit-theory-2026-10-30",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })


def save_vector(fig: plt.Figure, output: Path, stem: str, title: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f"{stem}.pdf", metadata={
        "Title": title,
        "Subject": "Deterministic mathematical illustration; no experimental data",
        "Creator": "plot_theory_figures.py (Matplotlib)",
        "CreationDate": None,
        "ModDate": None,
    })
    svg_path = output / f"{stem}.svg"
    fig.savefig(svg_path, metadata={
        "Title": title,
        "Creator": "plot_theory_figures.py (Matplotlib)",
        "Date": None,
    })
    # Matplotlib leaves trailing spaces in multiline SVG path data.
    svg_path.write_text("\n".join(line.rstrip() for line in
                        svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
                        encoding="utf-8")
    plt.close(fig)
    print(f"Wrote {stem}.pdf and {stem}.svg")


def clip_polygon(poly: np.ndarray, normal: np.ndarray, bound: float) -> np.ndarray:
    """Intersect a convex polygon with normal . x <= bound."""
    if not len(poly):
        return np.empty((0, 2))
    result = []
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        fa, fb = float(normal @ a - bound), float(normal @ b - bound)
        inside_a, inside_b = fa <= 1e-12, fb <= 1e-12
        if inside_a:
            result.append(a)
        if inside_a != inside_b:
            result.append(a + fa / (fa - fb) * (b - a))
    return np.asarray(result).reshape(-1, 2)


def power_cells(points: np.ndarray, weights: np.ndarray, window: tuple) -> list[np.ndarray]:
    """Power cells intersected with a *drawing window*, only for filling."""
    xmin, xmax, ymin, ymax = window
    cells = []
    for i, p in enumerate(points):
        poly = np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]])
        for k, pk in enumerate(points):
            if k != i:
                normal = 2 * (pk - p)
                bound = float(pk @ pk - p @ p + weights[i] - weights[k])
                poly = clip_polygon(poly, normal, bound)
        cells.append(poly)
    return cells


def pair_face(points: np.ndarray, weights: np.ndarray, i: int, j: int):
    """Return connector point, unit bisector direction, and full-plane interval.

    The face is q + s*v for lo <= s <= hi; None denotes an empty face.
    Equal endpoints are deliberately retained as a degenerate singleton.
    """
    delta = points[j] - points[i]
    d2 = float(delta @ delta)
    if d2 <= 0:
        raise ValueError("Selected sites must be distinct")
    q = points[i] + (0.5 + (weights[i] - weights[j]) / (2 * d2)) * delta
    v = np.array([-delta[1], delta[0]]) / np.sqrt(d2)
    lo, hi = -np.inf, np.inf
    pi = float((q - points[i]) @ (q - points[i]) - weights[i])
    for k, pk in enumerate(points):
        if k in (i, j):
            continue
        gap = float((q - pk) @ (q - pk) - weights[k] - pi)
        slope = float(2 * (pk - points[i]) @ v)
        if abs(slope) < 1e-12:
            if gap < -1e-12:
                return q, v, None
        elif slope > 0:
            hi = min(hi, gap / slope)
        else:
            lo = max(lo, gap / slope)
    return q, v, None if lo > hi + 1e-12 else (lo, hi)


def visible_segment(q: np.ndarray, v: np.ndarray, interval: tuple | None, window: tuple):
    """Limit a true face to the viewport, without adding viewport boundaries."""
    if interval is None:
        return None
    lo, hi = interval
    for coord, low, high in zip(range(2), window[::2], window[1::2]):
        if abs(v[coord]) < 1e-12:
            if not low <= q[coord] <= high:
                return None
        else:
            ends = sorted(((low - q[coord]) / v[coord], (high - q[coord]) / v[coord]))
            lo, hi = max(lo, ends[0]), min(hi, ends[1])
    if hi - lo <= 1e-12:
        return None
    return np.array([q + lo * v, q + hi * v])


def draw_cells(ax, points: np.ndarray, weights: np.ndarray, window: tuple) -> None:
    for i, poly in enumerate(power_cells(points, weights, window)):
        if len(poly):
            ax.add_patch(Polygon(poly, facecolor=CELL_COLORS[i], edgecolor="none", zorder=0))
    for i, j in combinations(range(len(points)), 2):
        segment = visible_segment(*pair_face(points, weights, i, j), window)
        if segment is not None:
            ax.plot(*segment.T, color="#A6A6A6", lw=0.8, zorder=1)
    ax.set(xlim=window[:2], ylim=window[2:])
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")


def label_site(ax, xy, label: str, offset: tuple) -> None:
    ax.annotate(label, xy, xytext=offset, textcoords="offset points",
                ha="center", va="center", fontsize=10.8, zorder=8)


def draw_realization(output: Path) -> None:
    expected = [None, (-1.5, -0.5), (-0.5, 0.5)]
    fig = plt.figure(figsize=(5.70, 2.95))
    headers = ["(a) No shared face", "(b) Face away from connector", "(c) Connector inside face"]
    for panel, weights in enumerate(FACE_WEIGHTS):
        ax = fig.add_axes([0.018 + panel * 0.334, 0.17, 0.312, 0.72])
        draw_cells(ax, FOUR_SITES, weights, FACE_WINDOW)
        q, v, interval = pair_face(FOUR_SITES, weights, 0, 1)
        assert interval == expected[panel]
        # The site connector and the entire pair bisector stay fixed.
        ax.plot([0, 2], [0, 0], color="#6C6C6C", lw=0.75, zorder=2)
        ax.plot([1, 1], FACE_WINDOW[2:], color=INK, lw=0.85,
                linestyle=(0, (3, 3)), zorder=2)
        if interval is not None:
            face = np.array([q + interval[0] * v, q + interval[1] * v])
            ax.plot(*face.T, color=BLUE, lw=3.0, solid_capstyle="butt", zorder=4)
            ax.scatter(face[:, 0], face[:, 1], s=13, color=BLUE, zorder=5)
        ax.scatter(FOUR_SITES[:, 0], FOUR_SITES[:, 1], s=17,
                   facecolor=INK, edgecolor="white", linewidth=0.35, zorder=6)
        ax.scatter(*q, marker="D", s=28, facecolor="white", edgecolor=INK,
                   linewidth=0.95, zorder=7)
        for p, label, offset in zip(FOUR_SITES, [r"$p_1$", r"$p_2$", r"$p_3$", r"$p_4$"],
                                    [(-7, -12), (7, -12), (-12, 5), (-12, 0)]):
            label_site(ax, p, label, offset)
        label_site(ax, q, r"$q_{12}$", (13, 9))
        ax.text(-0.38, -0.70, r"$C_1$", color=BLUE, fontsize=9.8, ha="center")
        ax.text(2.38, -0.70, r"$C_2$", color=ORANGE, fontsize=9.8, ha="center")
        ax.text(1.50, 1.21, r"$C_3$", color="#656565", fontsize=9.8, ha="center")
        ax.text(1., -1.80, r"$C_4$", color="#656565", fontsize=9.8, ha="center",
                bbox=dict(facecolor=CELL_COLORS[3], edgecolor="none", pad=0.2))
        if panel == 0:
            ax.text(1.64, -0.98, r"$F_{12}=\varnothing$", color=BLUE, ha="center", fontsize=10.8)
        elif panel == 1:
            ax.text(1.16, -1.02, r"$F_{12}$", color=BLUE, fontsize=10.8)
        else:
            ax.text(0.49, 0.30, r"$F_{12}$", color=BLUE, fontsize=10.8)
            ax.plot([1.12, 1.50], [-0.5, -0.5], color=BLUE, lw=0.55)
            ax.plot([1.12, 1.50], [0., 0.], color=BLUE, lw=0.55)
            ax.annotate("", xy=(1.44, -0.5), xytext=(1.44, 0),
                        arrowprops=dict(arrowstyle="|-|", color=BLUE, lw=0.8,
                                        shrinkA=0, shrinkB=0), zorder=5)
            ax.text(1.56, -0.25, r"$\frac{1}{2}$", fontsize=11.2, color=BLUE, va="center")
        center = 0.174 + panel * 0.334
        fig.text(center, 0.944, headers[panel], ha="center", va="center", fontsize=9.7)
        pair = [(1, 1), (1, -3), (-1, -1)][panel]
        fig.text(center, 0.134, rf"$(w_3,w_4)=({pair[0]},{pair[1]})$", ha="center", fontsize=10.5)
    fig.legend(handles=[
        Line2D([0], [0], color=INK, lw=0.85, linestyle=(0, (3, 3)), label=r"bisector $H_{12}$"),
        Line2D([0], [0], color=BLUE, lw=3., label="shared face"),
        Line2D([0], [0], color=INK, marker="D", markerfacecolor="white", markersize=4.5,
               linestyle="none", label="connector point"),
    ], loc="lower center", bbox_to_anchor=(0.5, -0.004), ncol=3,
        frameon=False, fontsize=9.2, handlelength=1.8, columnspacing=1.3)
    save_vector(fig, output, "figure_04_realization", "Fixed bisector, three realized-face outcomes")
    print("Section 4: F12 = empty, [-3/2,-1/2], [-1/2,1/2]; sigma = -1,-1,1; c(c)=1/2")


def draw_separators(output: Path) -> None:
    points = np.array([[0., 0.], [2., 0.]])
    window = (-0.45, 2.45, -0.68, 0.85)
    fig = plt.figure(figsize=(5.70, 2.15))
    for panel, weights in enumerate([np.array([0., 0.]), np.array([0., 2.])]):
        ax = fig.add_axes([0.035 + panel * 0.50, 0.22, 0.43, 0.63])
        draw_cells(ax, points, weights, window)
        q, _, interval = pair_face(points, weights, 0, 1)
        assert interval == (-np.inf, np.inf)
        assert q[0] == (1. if panel == 0 else 0.5)
        ax.plot([q[0], q[0]], window[2:], color=BLUE, lw=2.5, zorder=3)
        ax.plot([0., 2.], [0., 0.], color="#6C6C6C", lw=0.75, zorder=4)
        ax.scatter(points[:, 0], points[:, 1], s=22, facecolor=INK,
                   edgecolor="white", linewidth=0.35, zorder=5)
        ax.scatter(*q, marker="D", s=28, facecolor="white", edgecolor=INK,
                   linewidth=0.95, zorder=6)
        label_site(ax, points[0], r"$p_i$", (-4, -11))
        label_site(ax, points[1], r"$p_j$", (4, -11))
        ax.text(0.02, -0.55, r"$C_i$", color=BLUE, fontsize=11.0)
        ax.text(1.83, -0.55, r"$C_j$", color=ORANGE, fontsize=11.0)
        ax.text(q[0] + 0.10, 0.69, r"$H_{ij}$", color=BLUE, fontsize=11.2)
        fraction = r"\frac{1}{2}" if panel == 0 else r"\frac{1}{4}"
        ax.text(q[0] + 0.12, 0.12, rf"$t_{{ij}}={fraction}$", fontsize=11.2)
        if panel == 1:
            ax.plot([1., 1.], [0.34, 0.52], color=GREY, lw=0.75)
            ax.annotate("", xy=(0.5, 0.43), xytext=(1., 0.43),
                        arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.1,
                                        shrinkA=0, shrinkB=1.5), zorder=5)
        center = 0.25 + panel * 0.50
        title = "(a) Equal weights" if panel == 0 else r"(b) Increasing $w_j$"
        fig.text(center, 0.94, title, ha="center", fontsize=11.)
        value = 0 if panel == 0 else 2
        fig.text(center, 0.105, rf"$(w_i,w_j)=(0,{value})$", ha="center", fontsize=11.)
    save_vector(fig, output, "figure_02_separators", "Weight difference moves a two-site separator")
    print("Section 2: separator x = 1, 1/2; t = 1/2, 1/4; shifted difference = -2")


def cycle_data():
    """Assigned observation orientations and a signed *undirected* cycle."""
    return [(0, 1), (1, 2), (0, 2)], np.array([0., 0., 1.]), np.array([1., 1., -1.])


def draw_cycle(output: Path) -> None:
    edges, targets, traversal = cycle_data()
    assert traversal @ targets == -1
    vertices = np.array([[0., 0.], [1., 1.22], [2., 0.]])
    fig = plt.figure(figsize=(5.70, 2.30))
    ax = fig.add_axes([0.025, 0.04, 0.515, 0.92])
    ax.set(xlim=(-0.6, 2.6), ylim=(-0.77, 1.55))
    ax.set_aspect("equal")
    ax.axis("off")
    for (i, j), target in zip(edges, targets):
        ax.add_patch(FancyArrowPatch(vertices[i], vertices[j], arrowstyle="-|>",
                     mutation_scale=12, lw=1.25, color=BLUE, shrinkA=10, shrinkB=10))
        if (i, j) == (0, 1):
            label_position = (0.15, 0.80)
        elif (i, j) == (1, 2):
            label_position = (1.85, 0.80)
        else:
            label_position = (1., 0.16)
        ax.text(*label_position, rf"$z_{{{i+1}{j+1}}}={int(target)}$",
                ha="center", va="center", fontsize=11.8, color=BLUE)
    # This dashed arrow traverses the existing 1->3 observation backwards.
    # It is not a fourth observation and not a difference-constraint arc.
    ax.add_patch(FancyArrowPatch(vertices[2], vertices[0], connectionstyle="arc3,rad=-0.42",
                 arrowstyle="-|>", mutation_scale=12, lw=1.1, color=ORANGE,
                 linestyle=(0, (3, 2.4)), shrinkA=11, shrinkB=11))
    ax.text(1., -0.61, r"cycle return: $-z_{13}$", ha="center", fontsize=10.4, color=ORANGE)
    for i, p in enumerate(vertices):
        ax.add_patch(Circle(p, 0.125, facecolor="white", edgecolor=INK, lw=0.95, zorder=5))
        ax.text(*p, str(i + 1), ha="center", va="center", fontsize=12.3, zorder=6)
    fig.text(0.765, 0.79, "Cycle traversal", ha="center", fontsize=10.7)
    fig.text(0.765, 0.64, r"$1\to2\to3\to1$", ha="center", fontsize=12.3)
    fig.text(0.765, 0.43, "Signed sum", ha="center", fontsize=10.7)
    fig.text(0.765, 0.29, r"$z_{12}+z_{23}-z_{13}$", ha="center", fontsize=12.1)
    fig.text(0.765, 0.13, r"$=0+0-1=-1\ne0$", ha="center", fontsize=11.8)
    save_vector(fig, output, "figure_03_cycle", "Signed traversal of an incompatible observation cycle")
    print("Section 3: assigned arrows 1->2,2->3,1->3; traversal signs +,+,-; cycle sum -1")


def workflow_routes():
    """The actual drawn routes, checked against the frozen pyvoro2 0.6.3 source.

    'weights' is the evaluated-weight junction after optional alignment/blending.
    Connector diagnostics are separate Section 4 evaluations, not matcher fields.
    Finalization is described in the caption and Section 5.4, outside this loop.
    """
    specs = [
        ("observations", "fit", "main", [(2.05, 3.61), (2.05, 3.34)]),
        ("fit", "weights", "main", [(2.05, 2.66), (2.05, 2.50)]),
        ("weights", "tessellation", "main", [(2.05, 2.50), (2.05, 2.29)]),
        ("tessellation", "matching", "main", [(2.05, 1.77), (2.05, 1.40)]),
        ("matching", "outputs", "main", [(2.05, 0.84), (2.05, 0.545)]),
        ("observations", "matching", "candidates",
         [(0.925, 3.85), (0.13, 3.85), (0.13, 1.12), (0.925, 1.12)]),
        ("weights", "residuals", "diagnostic",
         [(2.05, 2.50), (3.40, 2.50), (3.40, 2.72), (3.65, 2.72)]),
        ("weights", "connector", "diagnostic",
         [(2.05, 2.50), (3.40, 2.50), (3.40, 1.97), (3.65, 1.97)]),
        ("matching", "streaks", "feedback", [(3.175, 1.12), (3.65, 1.12)]),
        ("streaks", "active", "feedback", [(4.575, 0.80), (4.575, 0.545)]),
        ("active", "fit", "feedback",
         [(5.50, 0.32), (5.61, 0.32), (5.61, 3.45), (3.40, 3.45),
          (3.40, 3.18), (3.175, 3.18)]),
    ]
    return [dict(source=s, target=t, kind=k, points=p) for s, t, k, p in specs]


def workflow_box(ax, center, size, lines, optional=False, diagnostic=False):
    """A box with explicitly placed (text, vertical offset, size) lines."""
    x, y = center
    width, height = size
    color = ORANGE if optional else GREY if diagnostic else BLUE
    fill = "#FFF7F1" if optional else "white" if diagnostic else "#F1F6FB"
    ax.add_patch(Rectangle((x - width / 2, y - height / 2), width, height,
                          facecolor=fill, edgecolor=color, lw=0.9, zorder=4))
    for label, offset, fontsize in lines:
        ax.text(x, y + offset, label, ha="center", va="center", fontsize=fontsize, zorder=5)


def draw_workflow(output: Path) -> None:
    fig = plt.figure(figsize=(5.70, 4.20))
    ax = fig.add_axes([0., 0., 1., 1.])
    ax.set(xlim=(0., 5.70), ylim=(0., 4.20))
    ax.set_aspect("equal")
    ax.axis("off")
    for route in workflow_routes():
        points = route["points"]
        color = ORANGE if route["kind"] == "feedback" else GREY if route["kind"] == "diagnostic" else BLUE
        style = (0, (3.5, 2.5)) if route["kind"] == "feedback" else "-"
        path = MplPath(points, [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1))
        arrowstyle = "-" if route["target"] == "weights" else "-|>"
        ax.add_patch(FancyArrowPatch(path=path, arrowstyle=arrowstyle, mutation_scale=9,
                     lw=0.95, color=color, linestyle=style, zorder=2))
    ax.scatter([2.05, 3.40], [2.50, 2.50], s=8, color=GREY, zorder=3)
    main_size = (2.25, 0.48)
    workflow_box(ax, (2.05, 3.85), main_size, [
        ("Resolved observations", 0.10, 10.5),
        ("fixed pairs, targets, images", -0.10, 9.2),
    ])
    workflow_box(ax, (2.05, 3.00), (2.25, 0.68), [
        ("Fixed-observation fit", 0.18, 10.5),
        ("all rows in one pass", -0.015, 9.3),
        ("active rows in refinement", -0.19, 9.3),
    ])
    ax.text(1.91, 2.48, "evaluated\nweights", ha="right", va="center", fontsize=9.2)
    workflow_box(ax, (2.05, 2.03), (2.25, 0.52), [
        ("Power tessellation", 0.10, 10.5),
        ("fixed sites and domain", -0.10, 9.3),
    ])
    workflow_box(ax, (2.05, 1.12), (2.25, 0.56), [
        ("Requested pair/image", 0.10, 10.5),
        ("matching", -0.10, 10.5),
    ])
    workflow_box(ax, (2.05, 0.32), (2.25, 0.45), [("Fit and face diagnostics", 0., 10.3)])
    ax.text(0.49, 2.13, "all\ncandidates", ha="center", va="center", fontsize=10.0, color=BLUE)
    workflow_box(ax, (4.575, 2.72), (1.85, 0.56), [
        ("Target residuals", 0.10, 10.3),
        ("all candidate rows", -0.10, 9.2),
    ], diagnostic=True)
    workflow_box(ax, (4.575, 1.97), (1.85, 0.60), [
        ("visibility and clearance", -0.015, 10.0),
        ("with competitor geometry", -0.19, 8.9),
    ], diagnostic=True)
    ax.text(287.515 / 72, 151.9 / 72, "Connector diagnostics",
            ha="left", va="baseline", fontsize=9.4,
            color=(0.145, 0.145, 0.145), zorder=5)
    workflow_box(ax, (4.575, 1.12), (1.85, 0.64), [
        ("Add/drop streaks", 0.12, 10.3),
        ("requested-image mask only", -0.12, 9.0),
    ], optional=True)
    workflow_box(ax, (4.575, 0.32), (1.85, 0.45), [("Next active subset", 0., 10.3)], optional=True)
    ax.text(4.48, 3.86, "Optional refinement", color=ORANGE, ha="center", fontsize=10.8)
    ax.text(4.48, 3.66, "dashed arrows", color=ORANGE, ha="center", fontsize=9.5)
    ax.text(4.43, 3.20, "if another iteration executes", color=ORANGE,
            ha="center", fontsize=9.0)
    save_vector(fig, output, "figure_05_workflow", "One-pass fitting and optional requested-face feedback")
    print("Section 5: all-candidate matching; only requested-image matches enter feedback")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure", choices=["all", "realization", "separators", "cycle", "workflow"], default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("manuscript/figures"))
    args = parser.parse_args()
    configure_style()
    if args.figure in ("all", "realization"):
        draw_realization(args.output_dir)
    if args.figure in ("all", "separators"):
        draw_separators(args.output_dir)
    if args.figure in ("all", "cycle"):
        draw_cycle(args.output_dir)
    if args.figure in ("all", "workflow"):
        draw_workflow(args.output_dir)


if __name__ == "__main__":
    main()
