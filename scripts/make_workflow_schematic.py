#!/usr/bin/env python3
"""Generate a cleaner workflow schematic for the manuscript.

The figure is intentionally schematic rather than data-bearing. It summarizes
four stages of the paper's workflow:

(a) sparse local separator observations on a candidate graph;
(b) a fixed-row inverse fit on those observations;
(c) realization checks in the fitted power tessellation; and
(d) active-support cleanup / refit.

The drawing uses exact half-space clipping for the 2D power cells so that the
manuscript-facing PDF remains vector-native rather than being driven by a
rasterized argmin grid.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib as mpl
mpl.use('Agg')
mpl.rcParams['pdf.fonttype'] = 42
mpl.rcParams['ps.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
import numpy as np

from _figure_io import save_figure_pair


ACCENT = '#1f4e79'
WARN = '#c23b22'
GRAY = '#b7c0cc'
LIGHT_GRAY = '#d9dee7'
DROP = '#8e839f'
DARK = '#33404d'
OBS = '#d08c00'
CELL_EDGE = '#7f8c99'
BG = '#ffffff'

# Mild geometry chosen to keep every site visually attached to a visible cell.
POINTS = np.array(
    [
        [0.16, 0.73],
        [0.42, 0.86],
        [0.78, 0.74],
        [0.20, 0.30],
        [0.55, 0.46],
        [0.82, 0.22],
    ],
    dtype=float,
)

# A small nonzero weight pattern is enough to make the inverse-fit panel read as
# weighted rather than purely Voronoi, while still keeping the power cells mild.
WEIGHTS = np.array([0.020, 0.010, -0.010, 0.000, 0.015, -0.005], dtype=float)

# Candidate graph shown in panel (a). It is intentionally sparse and only keeps
# the edges needed to tell the story.
CANDIDATE_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 3),
    (0, 4),
    (1, 2),
    (1, 3),
    (1, 4),
    (2, 4),
    (2, 5),
    (3, 4),
    (4, 5),
)

# Observed rows chosen for the inverse fit. The row (1, 3) is the didactic
# inconsistent example: it is kept in the fit, but no realized interface appears
# for that pair in the fitted tessellation.
OBSERVED_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 3),
    (1, 2),
    (1, 3),
    (2, 4),
    (3, 4),
    (4, 5),
)
FAILED_EDGE = (1, 3)
CLEANED_SUPPORT: tuple[tuple[int, int], ...] = tuple(edge for edge in OBSERVED_EDGES if edge != FAILED_EDGE)

PANEL_LABELS = ('(a)', '(b)', '(c)', '(d)')
BOX_BOUNDS = (0.0, 1.0, 0.0, 1.0)


@dataclass(frozen=True)
class CellArtist:
    polygon: np.ndarray
    center: np.ndarray


def _lighten(color: tuple[float, ...], factor: float = 0.70) -> tuple[float, float, float, float]:
    rgba = np.array(mpl.colors.to_rgba(color), dtype=float)
    rgb = 1.0 - factor * (1.0 - rgba[:3])
    return (float(rgb[0]), float(rgb[1]), float(rgb[2]), float(rgba[3]))


def _pastel_colors(n: int) -> list[tuple[float, float, float, float]]:
    base = plt.cm.Set3(np.linspace(0.0, 1.0, int(max(n, 3))))
    return [_lighten(color, factor=0.76) for color in base[:n]]


def _separator_fraction(points: np.ndarray, weights: np.ndarray, i: int, j: int) -> float:
    d = points[j] - points[i]
    denom = float(np.dot(d, d))
    if denom <= 0.0:
        return 0.5
    t = 0.5 + float(weights[i] - weights[j]) / (2.0 * denom)
    return float(np.clip(t, 0.10, 0.90))


def _clip_polygon_halfspace(
    polygon: list[np.ndarray],
    normal: np.ndarray,
    offset: float,
    *,
    eps: float = 1.0e-10,
) -> list[np.ndarray]:
    """Clip a convex polygon against ``normal · x <= offset``."""
    if not polygon:
        return []

    out: list[np.ndarray] = []
    wrapped = polygon[1:] + polygon[:1]
    for a, b in zip(polygon, wrapped):
        da = float(np.dot(normal, a) - offset)
        db = float(np.dot(normal, b) - offset)
        a_inside = da <= eps
        b_inside = db <= eps
        if a_inside and b_inside:
            out.append(b.copy())
            continue
        if a_inside == b_inside:
            continue
        denom = da - db
        if abs(denom) <= eps:
            continue
        t = da / denom
        point = a + t * (b - a)
        out.append(point)
        if b_inside:
            out.append(b.copy())

    if not out:
        return []

    cleaned: list[np.ndarray] = []
    for point in out:
        if not cleaned or float(np.linalg.norm(cleaned[-1] - point)) > 1.0e-9:
            cleaned.append(point)
    if len(cleaned) > 1 and float(np.linalg.norm(cleaned[0] - cleaned[-1])) <= 1.0e-9:
        cleaned.pop()
    return cleaned


def _power_cell(points: np.ndarray, weights: np.ndarray, index: int) -> np.ndarray:
    x0, x1, y0, y1 = BOX_BOUNDS
    polygon = [
        np.array((x0, y0), dtype=float),
        np.array((x1, y0), dtype=float),
        np.array((x1, y1), dtype=float),
        np.array((x0, y1), dtype=float),
    ]
    p_i = points[index]
    for j, p_j in enumerate(points):
        if j == index:
            continue
        normal = 2.0 * (p_j - p_i)
        offset = float(np.dot(p_j, p_j) - weights[j] - np.dot(p_i, p_i) + weights[index])
        polygon = _clip_polygon_halfspace(polygon, normal, offset)
        if not polygon:
            raise RuntimeError(f'power cell vanished for site {index}')
    return np.vstack(polygon)


def _build_cells(points: np.ndarray, weights: np.ndarray) -> list[CellArtist]:
    artists: list[CellArtist] = []
    for idx in range(points.shape[0]):
        poly = _power_cell(points, weights, idx)
        artists.append(CellArtist(polygon=poly, center=np.mean(poly, axis=0)))
    return artists


def _decorate_axis(ax: plt.Axes, *, label: str) -> None:
    ax.set_facecolor(BG)
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect('equal', adjustable='box')
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(
        -0.10,
        1.00,
        label,
        transform=ax.transAxes,
        ha='right',
        va='top',
        fontsize=12.4,
        fontweight='bold',
        color=DARK,
        clip_on=False,
    )


def _plot_graph(
    ax: plt.Axes,
    points: np.ndarray,
    edges: Iterable[tuple[int, int]],
    *,
    color: str = GRAY,
    linewidth: float = 1.2,
    linestyle: str | tuple[float, tuple[float, ...]] = '-',
    alpha: float = 1.0,
    zorder: float = 2.0,
) -> None:
    for i, j in edges:
        ax.plot(
            [float(points[i, 0]), float(points[j, 0])],
            [float(points[i, 1]), float(points[j, 1])],
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
            alpha=alpha,
            zorder=zorder,
            solid_capstyle='round',
            dash_capstyle='round',
        )


def _plot_separator_ticks(ax: plt.Axes, points: np.ndarray, weights: np.ndarray, edges: Iterable[tuple[int, int]]) -> None:
    for i, j in edges:
        p0 = points[i]
        p1 = points[j]
        t = _separator_fraction(points, weights, i, j)
        center = (1.0 - t) * p0 + t * p1
        direction = p1 - p0
        norm = float(np.linalg.norm(direction))
        if norm <= 0.0:
            continue
        direction /= norm
        normal = np.array([-direction[1], direction[0]], dtype=float)
        half_length = 0.018
        a = center - half_length * normal
        b = center + half_length * normal
        ax.plot(
            [float(a[0]), float(b[0])],
            [float(a[1]), float(b[1])],
            color=OBS,
            linewidth=2.0,
            solid_capstyle='round',
            zorder=4,
        )


def _plot_sites(ax: plt.Axes, points: np.ndarray, *, node_values: np.ndarray | None = None) -> None:
    if node_values is None:
        ax.scatter(points[:, 0], points[:, 1], s=34, c='black', linewidths=0.0, zorder=6)
        return
    norm = mpl.colors.Normalize(vmin=float(np.min(node_values)), vmax=float(np.max(node_values)))
    ax.scatter(
        points[:, 0],
        points[:, 1],
        s=140,
        c=node_values,
        cmap='coolwarm',
        norm=norm,
        edgecolors='black',
        linewidths=0.6,
        zorder=7,
    )


def _plot_power_cells(ax: plt.Axes, cells: list[CellArtist], colors: list[tuple[float, float, float, float]]) -> None:
    for color, artist in zip(colors, cells):
        patch = MplPolygon(
            artist.polygon,
            closed=True,
            facecolor=color,
            edgecolor=CELL_EDGE,
            linewidth=1.15,
            antialiased=True,
            joinstyle='round',
            zorder=0,
        )
        ax.add_patch(patch)


def _panel_a(ax: plt.Axes, points: np.ndarray, weights: np.ndarray) -> None:
    _plot_graph(ax, points, CANDIDATE_EDGES, color=GRAY, linewidth=1.15, alpha=0.95, zorder=1.5)
    _plot_graph(ax, points, OBSERVED_EDGES, color=ACCENT, linewidth=2.35, zorder=2.5)
    _plot_separator_ticks(ax, points, weights, OBSERVED_EDGES)
    _plot_sites(ax, points)


def _panel_b(ax: plt.Axes, points: np.ndarray, weights: np.ndarray) -> None:
    _plot_graph(ax, points, OBSERVED_EDGES, color=ACCENT, linewidth=2.35, zorder=2.5)
    _plot_sites(ax, points, node_values=weights)


def _panel_c(ax: plt.Axes, points: np.ndarray, cells: list[CellArtist], colors: list[tuple[float, float, float, float]]) -> None:
    _plot_power_cells(ax, cells, colors)
    _plot_graph(ax, points, CLEANED_SUPPORT, color=ACCENT, linewidth=2.10, zorder=2.8)
    _plot_graph(ax, points, [FAILED_EDGE], color=WARN, linewidth=1.95, linestyle=(0, (4.0, 2.3)), zorder=3.2)
    _plot_sites(ax, points)


def _panel_d(ax: plt.Axes, points: np.ndarray, cells: list[CellArtist], colors: list[tuple[float, float, float, float]]) -> None:
    _plot_power_cells(ax, cells, colors)
    _plot_graph(ax, points, OBSERVED_EDGES, color=DROP, linewidth=1.55, alpha=0.95, zorder=1.8)
    _plot_graph(ax, points, CLEANED_SUPPORT, color=ACCENT, linewidth=2.35, zorder=3.2)
    _plot_sites(ax, points)


def _add_global_legend(fig: plt.Figure) -> None:
    handles = [
        Line2D([0], [0], color=GRAY, linewidth=1.35),
        Line2D([0], [0], color=ACCENT, linewidth=2.35),
        Line2D([0], [0], color=OBS, linewidth=2.2),
        Line2D([0], [0], color=WARN, linewidth=2.0, linestyle=(0, (4.0, 2.3)), dash_capstyle='round'),
        Line2D([0], [0], color=DROP, linewidth=1.55),
    ]
    labels = [
        'candidate graph',
        'observed / retained rows',
        'separator offsets',
        'failed observed row',
        'dropped row after cleanup',
    ]
    fig.legend(
        handles,
        labels,
        loc='lower center',
        bbox_to_anchor=(0.5, 0.055),
        ncol=5,
        frameon=False,
        fontsize=12.0,
        handlelength=2.3,
        columnspacing=1.05,
        labelcolor=DARK,
    )


def build_figure(*, output: Path) -> None:
    points = POINTS
    weights = WEIGHTS
    cells = _build_cells(points, weights)
    colors = _pastel_colors(points.shape[0])

    fig, axes = plt.subplots(1, 4, figsize=(13.8, 3.55), facecolor='white')
    axes = np.atleast_1d(axes).ravel()
    fig.subplots_adjust(left=0.065, right=0.995, top=0.955, bottom=0.25, wspace=0.16)

    for ax, label in zip(axes, PANEL_LABELS):
        _decorate_axis(ax, label=label)

    _panel_a(axes[0], points, weights)
    _panel_b(axes[1], points, weights)
    _panel_c(axes[2], points, cells, colors)
    _panel_d(axes[3], points, cells, colors)
    _add_global_legend(fig)

    save_figure_pair(
        fig,
        png_path=output if output.suffix.lower() == '.png' else output.with_suffix('.png'),
        pdf_path=output.with_suffix('.pdf'),
        title=output.stem,
        png_dpi=300,
        bbox_inches='tight',
        facecolor='white',
    )
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--figure-path',
        type=Path,
        default=Path(__file__).resolve().parents[1] / 'build/legacy/figures/figure_powerfit_workflow_overview.png',
        help='PNG output path; a PDF with the same stem is written alongside it.',
    )
    args = parser.parse_args()
    build_figure(output=args.figure_path)
    print(f'Wrote workflow overview figure to {args.figure_path} and {args.figure_path.with_suffix(".pdf")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
