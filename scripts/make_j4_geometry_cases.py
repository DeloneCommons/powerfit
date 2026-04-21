#!/usr/bin/env python3
"""Build the manuscript-facing J4 geometry case-study figure."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
import numpy as np

from _figure_io import save_figure_pair


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRUCTURE_DIR = REPO_ROOT / 'data' / 'qtaim_showcase' / 'structures'
DEFAULT_QTAIM_DIR = REPO_ROOT / 'data' / 'qtaim_showcase' / 'qtaim'
DEFAULT_VORONOI_EDGES = (
    REPO_ROOT / 'results' / 'qtaim_showcase_voronoi' / 'voronoi_edges.csv'
)
DEFAULT_POWERFIT_EDGES = (
    REPO_ROOT / 'results' / 'qtaim_showcase_voronoi' / 'powerfit_edges.csv'
)
DEFAULT_OUTPUT_PDF = (
    REPO_ROOT / 'manuscript' / 'figures' / 'figure_J4_geometry_cases.pdf'
)
DEFAULT_OUTPUT_PNG = (
    REPO_ROOT / 'manuscript' / 'figures' / 'figure_J4_geometry_cases.png'
)

TRUE_EDGE = '0.34'
RAW_EXTRA = '#b23a3a'
VISIBLE_EXTRA = '#a71930'
SLIVER_EXTRA = '#2a6fbb'
SEPARATOR_TRACE = '#d08c00'
AUX_BOUNDARY = '0.65'
ATOM_EDGE = '0.20'

ELEMENT_STYLE = {
    'C': {'size': 34, 'facecolor': '0.28', 'edgecolor': '0.12'},
    'H': {'size': 18, 'facecolor': 'white', 'edgecolor': '0.25'},
    'O': {'size': 34, 'facecolor': '0.70', 'edgecolor': '0.20'},
}

VIEW_DEFAULTS = {
    'methane': (24.0, -32.0, 18.0),
    'benzene': (90.0, 0.0, -18.0),
    'adamantane': (26.0, -32.0, 42.0),
}


@dataclass(frozen=True)
class Atom:
    """Atom symbol and Cartesian coordinates."""

    symbol: str
    xyz: np.ndarray


@dataclass(frozen=True)
class Edge:
    """Archived showcase edge record."""

    system_key: str
    i: int
    j: int
    is_qtaim_edge: bool
    visible: bool
    clearance: float
    area: float


@dataclass(frozen=True)
class Projection:
    """2D projected coordinates plus depth ordering."""

    xy: np.ndarray
    depth: np.ndarray


@dataclass(frozen=True)
class PlaneProjection:
    """Projection into the motif section plane."""

    xy: np.ndarray
    depth: np.ndarray


@dataclass(frozen=True)
class MotifGeometry:
    """Local adamantane H-C-C-C-H motif data."""

    pair: tuple[int, int]
    path: list[int]
    plane_xy: np.ndarray
    plane_depth: np.ndarray
    box: tuple[float, float, float, float]


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {'1', 'true', 'yes', 'y'}


def _parse_view(raw: str) -> tuple[float, float, float]:
    parts = [float(part.strip()) for part in raw.split(',')]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError('views must be rx,ry,rz in degrees')
    return (parts[0], parts[1], parts[2])


def _read_xyz(path: Path) -> list[Atom]:
    lines = path.read_text(encoding='utf-8').splitlines()
    n_atoms = int(lines[0].strip())
    atoms: list[Atom] = []
    for line in lines[2 : 2 + n_atoms]:
        symbol, x, y, z = line.split()[:4]
        atoms.append(
            Atom(
                symbol=symbol,
                xyz=np.array([float(x), float(y), float(z)], dtype=float),
            )
        )
    return atoms


def _read_edges(path: Path) -> list[Edge]:
    out: list[Edge] = []
    with path.open('r', encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            out.append(
                Edge(
                    system_key=row['system_key'],
                    i=int(row['i']),
                    j=int(row['j']),
                    is_qtaim_edge=_parse_bool(row['is_qtaim_edge']),
                    visible=_parse_bool(row['intersection_inside']),
                    clearance=float(row['intersection_edge_min_dist']),
                    area=float(row['area']),
                )
            )
    return out


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _edges_for(edges: Iterable[Edge], system_key: str) -> list[Edge]:
    return [edge for edge in edges if edge.system_key == system_key]


def _rotation_matrix(view: tuple[float, float, float]) -> np.ndarray:
    rx, ry, rz = [math.radians(v) for v in view]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    my = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    mz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    return mz @ my @ mx


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        raise ValueError('expected non-zero vector')
    return vector / norm


def _project(
    atoms: list[Atom],
    view: tuple[float, float, float],
    *,
    subset: set[int] | None = None,
) -> Projection:
    coords = np.vstack([atom.xyz for atom in atoms])
    if subset:
        center = coords[sorted(subset)].mean(axis=0)
    else:
        center = coords.mean(axis=0)
    rotated = (coords - center) @ _rotation_matrix(view).T
    xy = rotated[:, :2]
    ref = xy[sorted(subset)] if subset else xy
    span = np.ptp(ref, axis=0)
    scale = max(float(span.max()), 1.0e-6)
    return Projection(xy=xy / scale, depth=rotated[:, 2])


def _project_with_axes(
    atoms: list[Atom],
    *,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    depth_axis: np.ndarray,
    subset: set[int] | None = None,
) -> Projection:
    coords = np.vstack([atom.xyz for atom in atoms])
    if subset:
        center = coords[sorted(subset)].mean(axis=0)
    else:
        center = coords.mean(axis=0)
    basis = np.vstack([x_axis, y_axis, depth_axis])
    rotated = (coords - center) @ basis.T
    xy = rotated[:, :2]
    ref = xy[sorted(subset)] if subset else xy
    span = np.ptp(ref, axis=0)
    scale = max(float(span.max()), 1.0e-6)
    return Projection(xy=xy / scale, depth=rotated[:, 2])


def _setup_axis(ax: plt.Axes) -> None:
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        0.02,
        0.98,
        f'({label})',
        transform=ax.transAxes,
        ha='left',
        va='top',
        fontsize=9.5,
        fontweight='bold',
    )


def _set_panel_limits(ax: plt.Axes, xy: np.ndarray, *, pad: float = 0.10) -> None:
    mins = xy.min(axis=0)
    maxs = xy.max(axis=0)
    span = np.maximum(maxs - mins, 1.0e-6)
    ax.set_xlim(mins[0] - pad * span[0], maxs[0] + pad * span[0])
    ax.set_ylim(mins[1] - pad * span[1], maxs[1] + pad * span[1])


def _padded_span(xy: np.ndarray, *, pad: float) -> np.ndarray:
    span = np.maximum(np.ptp(xy, axis=0), 1.0e-6)
    return span * (1.0 + 2.0 * pad)


def _draw_edges(
    ax: plt.Axes,
    proj: Projection,
    edges: Iterable[Edge],
    *,
    atom_subset: set[int] | None = None,
    include_true: bool = True,
    include_raw_extras: bool = True,
    include_visible_extras: bool = True,
    selected_extras: set[tuple[int, int]] | None = None,
    offset: tuple[float, float] = (0.0, 0.0),
    visible_alpha: float = 0.70,
) -> None:
    selected_extras = selected_extras or set()
    dx, dy = offset
    for edge in edges:
        pair = tuple(sorted((edge.i, edge.j)))
        if atom_subset is not None and (
            edge.i not in atom_subset or edge.j not in atom_subset
        ):
            continue
        if edge.is_qtaim_edge:
            if not include_true or not edge.visible:
                continue
            color = TRUE_EDGE
            linestyle = '-'
            linewidth = 0.78
            alpha = 0.46
            zorder = 1
        elif edge.visible:
            if not include_visible_extras:
                continue
            color = VISIBLE_EXTRA
            linestyle = '-'
            linewidth = 1.25 if pair in selected_extras else 0.95
            alpha = 0.95 if pair in selected_extras else visible_alpha
            zorder = 3
        else:
            if not include_raw_extras:
                continue
            color = RAW_EXTRA
            linestyle = (0, (0.9, 1.4))
            linewidth = 1.00 if pair in selected_extras else 0.82
            alpha = 0.78 if pair in selected_extras else 0.42
            zorder = 2 if pair in selected_extras else 0
        xs = [proj.xy[edge.i, 0] + dx, proj.xy[edge.j, 0] + dx]
        ys = [proj.xy[edge.i, 1] + dy, proj.xy[edge.j, 1] + dy]
        ax.plot(
            xs,
            ys,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            alpha=alpha,
            zorder=zorder,
        )


def _draw_atoms(
    ax: plt.Axes,
    atoms: list[Atom],
    proj: Projection,
    *,
    atom_subset: set[int] | None = None,
    offset: tuple[float, float] = (0.0, 0.0),
    alpha: float = 1.0,
    size_scale: float = 1.0,
) -> None:
    dx, dy = offset
    indices = range(len(atoms)) if atom_subset is None else sorted(atom_subset)
    for idx in sorted(indices, key=lambda item: proj.depth[item]):
        atom = atoms[idx]
        style = ELEMENT_STYLE.get(atom.symbol, ELEMENT_STYLE['C'])
        ax.scatter(
            [proj.xy[idx, 0] + dx],
            [proj.xy[idx, 1] + dy],
            s=style['size'] * size_scale,
            facecolors=style['facecolor'],
            edgecolors=style['edgecolor'],
            linewidths=0.55,
            alpha=alpha,
            zorder=5 + float(proj.depth[idx] > 0.0),
        )


def _draw_molecule(
    ax: plt.Axes,
    atoms: list[Atom],
    edges: list[Edge],
    *,
    view: tuple[float, float, float],
    atom_subset: set[int] | None = None,
    include_true: bool = True,
    include_raw_extras: bool = True,
    include_visible_extras: bool = True,
    selected_extras: set[tuple[int, int]] | None = None,
    offset: tuple[float, float] = (0.0, 0.0),
    atom_alpha: float = 1.0,
    atom_size_scale: float = 1.0,
    visible_alpha: float = 0.70,
) -> Projection:
    proj = _project(atoms, view, subset=atom_subset)
    _draw_edges(
        ax,
        proj,
        edges,
        atom_subset=atom_subset,
        include_true=include_true,
        include_raw_extras=include_raw_extras,
        include_visible_extras=include_visible_extras,
        selected_extras=selected_extras,
        offset=offset,
        visible_alpha=visible_alpha,
    )
    _draw_atoms(
        ax,
        atoms,
        proj,
        atom_subset=atom_subset,
        offset=offset,
        alpha=atom_alpha,
        size_scale=atom_size_scale,
    )
    return proj


def _true_edges(edges: Iterable[Edge]) -> list[Edge]:
    return [edge for edge in edges if edge.is_qtaim_edge and edge.visible]


def _visible_extra_edges(edges: Iterable[Edge]) -> list[Edge]:
    return [edge for edge in edges if edge.visible and not edge.is_qtaim_edge]


def _raw_extra_edges(edges: Iterable[Edge], *, min_area: float = 0.0) -> list[Edge]:
    return [
        edge
        for edge in edges
        if not edge.is_qtaim_edge and not edge.visible and edge.area >= min_area
    ]


def _edge_by_pair(edges: Iterable[Edge], pair: tuple[int, int]) -> Edge | None:
    target = tuple(sorted(pair))
    for edge in edges:
        if tuple(sorted((edge.i, edge.j))) == target:
            return edge
    return None


def _build_graph(edges: Iterable[Edge]) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        graph[edge.i].add(edge.j)
        graph[edge.j].add(edge.i)
    return graph


def _shortest_path(
    graph: dict[int, set[int]],
    start: int,
    goal: int,
) -> list[int]:
    queue: deque[int] = deque([start])
    parent: dict[int, int | None] = {start: None}
    while queue:
        node = queue.popleft()
        if node == goal:
            break
        for neighbor in sorted(graph.get(node, set())):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            queue.append(neighbor)
    if goal not in parent:
        raise ValueError('path not found in graph')
    out: list[int] = []
    node: int | None = goal
    while node is not None:
        out.append(node)
        node = parent[node]
    return list(reversed(out))


def _methane_roles(atoms: list[Atom]) -> dict[str, int]:
    carbon_index = next(idx for idx, atom in enumerate(atoms) if atom.symbol == 'C')
    hydrogen_indices = [idx for idx, atom in enumerate(atoms) if atom.symbol == 'H']
    rel = {idx: atoms[idx].xyz - atoms[carbon_index].xyz for idx in hydrogen_indices}
    top = next(idx for idx in hydrogen_indices if np.all(rel[idx] > 0.0))
    left = next(
        idx
        for idx in hydrogen_indices
        if rel[idx][0] < 0.0 and rel[idx][1] < 0.0 and rel[idx][2] > 0.0
    )
    overlap = [idx for idx in hydrogen_indices if idx not in {top, left}]
    if len(overlap) != 2:
        raise ValueError('expected exactly two overlapping methane hydrogens')
    return {
        'carbon': carbon_index,
        'top': top,
        'left': left,
        'overlap_front': overlap[0],
        'overlap_back': overlap[1],
    }


def _methane_projection(
    atoms: list[Atom],
    *,
    split_degrees: float,
) -> Projection:
    roles = _methane_roles(atoms)
    carbon = atoms[roles['carbon']].xyz
    top_vec = atoms[roles['top']].xyz - carbon
    overlap_front = atoms[roles['overlap_front']].xyz - carbon
    overlap_back = atoms[roles['overlap_back']].xyz - carbon

    y_axis = _normalize(top_vec)
    depth_axis = _normalize(overlap_front - overlap_back)
    x_axis = _normalize(np.cross(depth_axis, y_axis))

    theta = math.radians(split_degrees)
    x_rot = math.cos(theta) * x_axis + math.sin(theta) * depth_axis
    depth_rot = -math.sin(theta) * x_axis + math.cos(theta) * depth_axis
    return _project_with_axes(
        atoms,
        x_axis=x_rot,
        y_axis=y_axis,
        depth_axis=depth_rot,
    )


def _methane_separator_fraction(qtaim_json: dict) -> float:
    atoms = qtaim_json['atoms']
    fractions: list[float] = []
    for cp in qtaim_json['critical_points']:
        if cp.get('cp_type') != 'bcp':
            continue
        atom_i = int(cp['atom_i']) - 1
        atom_j = int(cp['atom_j']) - 1
        pos_i = np.array(atoms[atom_i]['position_angstrom'], dtype=float)
        pos_j = np.array(atoms[atom_j]['position_angstrom'], dtype=float)
        bcp = np.array(cp['position_angstrom'], dtype=float)
        if atoms[atom_i]['element'] == 'C':
            carbon = pos_i
            hydrogen = pos_j
        else:
            carbon = pos_j
            hydrogen = pos_i
        bond = hydrogen - carbon
        fractions.append(float(np.dot(bcp - carbon, bond) / np.dot(bond, bond)))
    if not fractions:
        raise ValueError('expected methane QTAIM file to contain C-H bond critical points')
    return float(np.mean(fractions))


def _methane_inplane_mean_bond_length(
    proj: Projection,
    roles: dict[str, int],
) -> float:
    carbon_xy = proj.xy[roles['carbon']]
    lengths = [
        float(np.linalg.norm(proj.xy[roles[name]] - carbon_xy))
        for name in ['top', 'left']
    ]
    return float(np.mean(lengths))


def _draw_methane_slice(
    ax: plt.Axes,
    *,
    atoms: list[Atom],
    separator_fraction: float,
    target_bond_fraction: float | None = None,
) -> None:
    _setup_axis(ax)
    roles = _methane_roles(atoms)
    proj = _methane_projection(atoms, split_degrees=0.0)

    carbon_xy = proj.xy[roles['carbon']]
    top_xy = proj.xy[roles['top']]
    left_xy = proj.xy[roles['left']]
    overlap_xy = proj.xy[roles['overlap_front']]

    overlap_bond = overlap_xy - carbon_xy
    overlap_perp = _normalize(np.array([-overlap_bond[1], overlap_bond[0]], dtype=float))
    overlap_shift = 0.022
    overlap_positions = np.vstack(
        [
            overlap_xy - overlap_shift * overlap_perp,
            overlap_xy + overlap_shift * overlap_perp,
        ]
    )

    ax.plot(
        [top_xy[0], left_xy[0]],
        [top_xy[1], left_xy[1]],
        color=RAW_EXTRA,
        linestyle=(0, (0.9, 1.4)),
        linewidth=1.05,
        alpha=0.70,
        zorder=0,
    )
    for hydrogen_xy in [top_xy, left_xy]:
        ax.plot(
            [carbon_xy[0], hydrogen_xy[0]],
            [carbon_xy[1], hydrogen_xy[1]],
            color=TRUE_EDGE,
            linewidth=0.92,
            alpha=0.56,
            zorder=1,
        )
    for overlap_pos in overlap_positions:
        ax.plot(
            [carbon_xy[0], overlap_pos[0]],
            [carbon_xy[1], overlap_pos[1]],
            color=TRUE_EDGE,
            linewidth=0.78,
            alpha=0.22,
            zorder=0.9,
        )

    separator_length = 0.38
    for hydrogen_xy in [top_xy, left_xy]:
        bond = hydrogen_xy - carbon_xy
        perp = _normalize(np.array([-bond[1], bond[0]], dtype=float))
        center = carbon_xy + separator_fraction * bond
        ends = np.vstack(
            [center - separator_length * perp, center + separator_length * perp]
        )
        ax.plot(
            ends[:, 0],
            ends[:, 1],
            color=SEPARATOR_TRACE,
            linewidth=1.10,
            alpha=0.95,
            solid_capstyle='round',
            zorder=2,
        )

    ax.scatter(
        [carbon_xy[0]],
        [carbon_xy[1]],
        s=40,
        facecolors=ELEMENT_STYLE['C']['facecolor'],
        edgecolors=ATOM_EDGE,
        linewidths=0.60,
        zorder=4,
    )
    ax.scatter(
        overlap_positions[:, 0],
        overlap_positions[:, 1],
        s=19,
        facecolors='white',
        edgecolors='0.66',
        linewidths=0.56,
        zorder=3,
    )
    ax.scatter(
        [top_xy[0], left_xy[0]],
        [top_xy[1], left_xy[1]],
        s=22,
        facecolors='white',
        edgecolors=ATOM_EDGE,
        linewidths=0.60,
        zorder=4,
    )
    ax.text(
        overlap_xy[0] + 0.006,
        overlap_xy[1] - 0.055,
        'out of plane',
        fontsize=6.4,
        color='0.45',
        ha='center',
        va='top',
        zorder=4,
    )

    panel_xy = np.vstack([carbon_xy, top_xy, left_xy, overlap_positions])
    if target_bond_fraction is None:
        pad = 0.31
    else:
        span_x = max(float(np.ptp(panel_xy[:, 0])), 1.0e-6)
        bond_length = float(
            np.mean(
                [
                    np.linalg.norm(top_xy - carbon_xy),
                    np.linalg.norm(left_xy - carbon_xy),
                ]
            )
        )
        target_panel_width = bond_length / max(target_bond_fraction, 1.0e-6)
        pad = max(0.18, 0.5 * (target_panel_width / span_x - 1.0))
    _set_panel_limits(ax, panel_xy, pad=pad)
    _panel_label(ax, 'b')


def _combined_benzene_edges(
    vor_edges: list[Edge],
    pow_edges: list[Edge],
    *,
    min_raw_area: float,
) -> list[Edge]:
    return [
        *_true_edges(pow_edges),
        *_raw_extra_edges(vor_edges, min_area=min_raw_area),
        *_visible_extra_edges(pow_edges),
    ]


def _draw_benzene_overlay_panel(
    ax: plt.Axes,
    *,
    atoms: list[Atom],
    vor_edges: list[Edge],
    pow_edges: list[Edge],
    view: tuple[float, float, float],
    panel_label: str,
    geometry_label: str,
    min_raw_area: float,
) -> None:
    _setup_axis(ax)
    proj = _draw_molecule(
        ax,
        atoms,
        _combined_benzene_edges(vor_edges, pow_edges, min_raw_area=min_raw_area),
        view=view,
    )
    _set_panel_limits(ax, proj.xy, pad=0.12)
    ax.text(
        0.58,
        0.05,
        geometry_label,
        transform=ax.transAxes,
        ha='center',
        va='bottom',
        fontsize=7.4,
    )
    _panel_label(ax, panel_label)


def _benzene_selected_para_pair(
    atoms: list[Atom],
    edges: Iterable[Edge],
) -> tuple[int, int]:
    visible_cc = [
        edge
        for edge in _visible_extra_edges(edges)
        if atoms[edge.i].symbol == 'C' and atoms[edge.j].symbol == 'C'
    ]
    if visible_cc:
        edge = min(visible_cc, key=lambda candidate: candidate.clearance)
        return tuple(sorted((edge.i, edge.j)))

    carbon_indices = [idx for idx, atom in enumerate(atoms) if atom.symbol == 'C']
    coords = np.vstack([atom.xyz for atom in atoms])
    best_pair: tuple[int, int] | None = None
    best_distance = -1.0
    for left_idx, left in enumerate(carbon_indices):
        for right in carbon_indices[left_idx + 1 :]:
            distance = float(np.linalg.norm(coords[left] - coords[right]))
            if distance > best_distance:
                best_distance = distance
                best_pair = (left, right)
    if best_pair is None:
        raise ValueError('expected benzene to contain carbon atoms')
    return tuple(sorted(best_pair))


def _draw_benzene_visible_pair(
    ax: plt.Axes,
    *,
    atoms_sym: list[Atom],
    atoms_broken: list[Atom],
    edges_sym: list[Edge],
    edges_broken: list[Edge],
    view: tuple[float, float, float],
) -> None:
    _setup_axis(ax)
    ax.text(
        0.50,
        0.97,
        'visible-mask view',
        transform=ax.transAxes,
        ha='center',
        va='top',
        fontsize=7.4,
    )
    selected_pair = _benzene_selected_para_pair(atoms_sym, edges_sym)
    sym_extra = _edge_by_pair(edges_sym, selected_pair)
    broken_extra = _edge_by_pair(edges_broken, selected_pair)

    sym_display = list(_true_edges(edges_sym))
    if sym_extra is not None and sym_extra.visible and not sym_extra.is_qtaim_edge:
        sym_display.append(sym_extra)
    broken_display = list(_true_edges(edges_broken))
    if broken_extra is not None and broken_extra.visible and not broken_extra.is_qtaim_edge:
        broken_display.append(broken_extra)

    _draw_molecule(
        ax,
        atoms_sym,
        sym_display,
        view=view,
        include_raw_extras=False,
        include_visible_extras=True,
        selected_extras={selected_pair},
        offset=(-0.70, 0.0),
    )
    _draw_molecule(
        ax,
        atoms_broken,
        broken_display,
        view=view,
        include_raw_extras=False,
        include_visible_extras=True,
        selected_extras={selected_pair},
        offset=(0.70, 0.0),
    )
    ax.text(
        0.25,
        0.05,
        'sym.',
        transform=ax.transAxes,
        ha='center',
        va='bottom',
        fontsize=7.4,
    )
    ax.text(
        0.78,
        0.05,
        'pert.',
        transform=ax.transAxes,
        ha='center',
        va='bottom',
        fontsize=7.4,
    )
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.62, 0.62)
    _panel_label(ax, 'e')


def _edge_pair_symbols(edge: Edge, atoms: list[Atom]) -> tuple[str, str]:
    return tuple(sorted((atoms[edge.i].symbol, atoms[edge.j].symbol)))


def _adamantane_visible_hh_triangles(
    atoms: list[Atom],
    edges: list[Edge],
) -> list[tuple[int, int, int]]:
    hh_edges = [
        tuple(sorted((edge.i, edge.j)))
        for edge in _visible_extra_edges(edges)
        if _edge_pair_symbols(edge, atoms) == ('H', 'H')
    ]
    graph: dict[int, set[int]] = defaultdict(set)
    for left, right in hh_edges:
        graph[left].add(right)
        graph[right].add(left)
    triangles: set[tuple[int, int, int]] = set()
    for left in sorted(graph):
        neighbors = sorted(graph[left])
        for idx, middle in enumerate(neighbors):
            for right in neighbors[idx + 1 :]:
                if right in graph[middle]:
                    triangles.add(tuple(sorted((left, middle, right))))
    return sorted(triangles)


def _adamantane_right_triangle(
    atoms: list[Atom],
    edges: list[Edge],
    *,
    view: tuple[float, float, float],
) -> tuple[int, int, int]:
    triangles = _adamantane_visible_hh_triangles(atoms, edges)
    if not triangles:
        raise ValueError('expected adamantane showcase to contain H-H triangles')
    proj = _project(atoms, view)
    return max(triangles, key=lambda tri: float(np.mean(proj.xy[list(tri), 0])))


def _adamantane_pair_for_local_motif(
    atoms: list[Atom],
    triangle: tuple[int, int, int],
    *,
    view: tuple[float, float, float],
) -> tuple[int, int]:
    proj = _project(atoms, view)
    pairs = [
        tuple(sorted((triangle[0], triangle[1]))),
        tuple(sorted((triangle[0], triangle[2]))),
        tuple(sorted((triangle[1], triangle[2]))),
    ]
    return max(
        pairs,
        key=lambda pair: float(np.mean(proj.xy[list(pair), 1])),
    )


def _draw_adamantane_global_panel(
    ax: plt.Axes,
    *,
    atoms: list[Atom],
    edges: list[Edge],
    view: tuple[float, float, float],
    triangle: tuple[int, int, int],
) -> Projection:
    _setup_axis(ax)
    proj = _project(atoms, view)

    for edge in _true_edges(edges):
        ax.plot(
            [proj.xy[edge.i, 0], proj.xy[edge.j, 0]],
            [proj.xy[edge.i, 1], proj.xy[edge.j, 1]],
            color=TRUE_EDGE,
            linewidth=0.78,
            alpha=0.46,
            zorder=1,
        )

    tri_pairs = {
        tuple(sorted((triangle[0], triangle[1]))),
        tuple(sorted((triangle[0], triangle[2]))),
        tuple(sorted((triangle[1], triangle[2]))),
    }
    for left, right in sorted(tri_pairs):
        ax.plot(
            [proj.xy[left, 0], proj.xy[right, 0]],
            [proj.xy[left, 1], proj.xy[right, 1]],
            color=VISIBLE_EXTRA,
            linewidth=1.10,
            alpha=0.96,
            zorder=3.1,
        )

    cc_slivers = [
        edge
        for edge in _visible_extra_edges(edges)
        if _edge_pair_symbols(edge, atoms) == ('C', 'C')
    ]
    for edge in cc_slivers:
        ax.plot(
            [proj.xy[edge.i, 0], proj.xy[edge.j, 0]],
            [proj.xy[edge.i, 1], proj.xy[edge.j, 1]],
            color=SLIVER_EXTRA,
            linewidth=1.24,
            linestyle=(0, (2.0, 1.4)),
            alpha=0.96,
            zorder=2.35,
        )

    _draw_atoms(ax, atoms, proj, alpha=0.88)
    _set_panel_limits(ax, proj.xy, pad=0.12)
    _panel_label(ax, 'f')
    return proj


def _motif_plane_basis(
    atoms: list[Atom],
    path: list[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    base_indices = [path[0], path[1], path[3], path[4]]
    base_points = np.vstack([atoms[idx].xyz for idx in base_indices])
    origin = base_points.mean(axis=0)
    _, _, vh = np.linalg.svd(base_points - origin)
    plane_normal = vh[-1]
    x_axis = atoms[path[4]].xyz - atoms[path[0]].xyz
    x_axis = x_axis - float(np.dot(x_axis, plane_normal)) * plane_normal
    x_axis = _normalize(x_axis)
    y_axis = -_normalize(np.cross(plane_normal, x_axis))
    depth_axis = _normalize(np.cross(x_axis, y_axis))
    return origin, x_axis, y_axis, depth_axis


def _project_into_motif_plane(
    atoms: list[Atom],
    *,
    origin: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    depth_axis: np.ndarray,
    scale_subset: list[int],
) -> PlaneProjection:
    coords = np.vstack([atom.xyz for atom in atoms])
    deltas = coords - origin
    xy = np.column_stack([deltas @ x_axis, deltas @ y_axis])
    depth = deltas @ depth_axis
    scale = max(float(np.ptp(xy[scale_subset], axis=0).max()), 1.0e-6)
    return PlaneProjection(xy=xy / scale, depth=depth / scale)


def _clip_polygon_halfplane(
    polygon: list[np.ndarray],
    A: np.ndarray,
    B: float,
    *,
    eps: float = 1.0e-9,
) -> list[np.ndarray]:
    if not polygon:
        return []

    def inside(point: np.ndarray) -> bool:
        return float(np.dot(A, point)) <= B + eps

    def intersection(point_i: np.ndarray, point_j: np.ndarray) -> np.ndarray:
        delta = point_j - point_i
        denom = float(np.dot(A, delta))
        if abs(denom) <= 1.0e-14:
            return point_j.copy()
        t = (B - float(np.dot(A, point_i))) / denom
        return point_i + t * delta

    out: list[np.ndarray] = []
    prev = polygon[-1]
    prev_inside = inside(prev)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not prev_inside:
                out.append(intersection(prev, current))
            out.append(current.copy())
        elif prev_inside:
            out.append(intersection(prev, current))
        prev = current
        prev_inside = current_inside

    cleaned: list[np.ndarray] = []
    for point in out:
        if not cleaned or float(np.linalg.norm(point - cleaned[-1])) > 1.0e-9:
            cleaned.append(point)
    if len(cleaned) > 1 and float(np.linalg.norm(cleaned[0] - cleaned[-1])) <= 1.0e-9:
        cleaned.pop()
    return cleaned


def _power_cell_polygon(
    atom_index: int,
    points_xy: np.ndarray,
    depths: np.ndarray,
    box: tuple[float, float, float, float],
) -> list[np.ndarray]:
    xmin, xmax, ymin, ymax = box
    polygon = [
        np.array([xmin, ymin], dtype=float),
        np.array([xmax, ymin], dtype=float),
        np.array([xmax, ymax], dtype=float),
        np.array([xmin, ymax], dtype=float),
    ]
    point_i = points_xy[atom_index]
    depth_i = float(depths[atom_index])
    for atom_j in range(points_xy.shape[0]):
        if atom_j == atom_index:
            continue
        point_j = points_xy[atom_j]
        depth_j = float(depths[atom_j])
        A = 2.0 * (point_j - point_i)
        B = float(np.dot(point_j, point_j) + depth_j * depth_j)
        B -= float(np.dot(point_i, point_i) + depth_i * depth_i)
        polygon = _clip_polygon_halfplane(polygon, A, B)
        if not polygon:
            break
    return polygon


def _label_polygon_edges(
    atom_index: int,
    polygon: list[np.ndarray],
    points_xy: np.ndarray,
    depths: np.ndarray,
    *,
    tol: float = 1.0e-4,
) -> list[int | None]:
    labels: list[int | None] = []
    point_i = points_xy[atom_index]
    depth_i = float(depths[atom_index])
    for idx in range(len(polygon)):
        point_a = polygon[idx]
        point_b = polygon[(idx + 1) % len(polygon)]
        midpoint = 0.5 * (point_a + point_b)
        best_label: int | None = None
        best_residual = float('inf')
        for atom_j in range(points_xy.shape[0]):
            if atom_j == atom_index:
                continue
            point_j = points_xy[atom_j]
            depth_j = float(depths[atom_j])
            residual = abs(
                float(np.dot(2.0 * (point_j - point_i), midpoint))
                - (
                    float(np.dot(point_j, point_j) + depth_j * depth_j)
                    - float(np.dot(point_i, point_i) + depth_i * depth_i)
                )
            )
            if residual < best_residual:
                best_residual = residual
                best_label = atom_j
        labels.append(best_label if best_residual <= tol else None)
    return labels


def _segment_key(
    point_a: np.ndarray,
    point_b: np.ndarray,
    neighbor: int | None,
    atom_i: int,
) -> tuple:
    rounded = sorted(
        [
            (round(float(point_a[0]), 4), round(float(point_a[1]), 4)),
            (round(float(point_b[0]), 4), round(float(point_b[1]), 4)),
        ]
    )
    label = tuple(sorted((atom_i, neighbor))) if neighbor is not None else ('box',)
    return (*rounded[0], *rounded[1], *label)


def _adamantane_local_motif(
    atoms: list[Atom],
    edges: list[Edge],
    selected_pair: tuple[int, int],
) -> MotifGeometry:
    graph = _build_graph(_true_edges(edges))
    path = _shortest_path(graph, selected_pair[0], selected_pair[1])
    symbols = [atoms[idx].symbol for idx in path]
    if len(path) != 5 or symbols != ['H', 'C', 'C', 'C', 'H']:
        raise ValueError('expected adamantane local motif to be H-C-C-C-H')

    origin, x_axis, y_axis, depth_axis = _motif_plane_basis(atoms, path)
    proj = _project_into_motif_plane(
        atoms,
        origin=origin,
        x_axis=x_axis,
        y_axis=y_axis,
        depth_axis=depth_axis,
        scale_subset=path,
    )
    ref_xy = proj.xy[path]
    x_span = max(float(np.ptp(ref_xy[:, 0])), 1.0e-6)
    y_span = max(float(np.ptp(ref_xy[:, 1])), 1.0e-6)
    x_pad = 0.30 * x_span
    y_pad = 0.42 * y_span
    xmin = float(ref_xy[:, 0].min() - x_pad)
    xmax = float(ref_xy[:, 0].max() + x_pad)
    ymin = float(ref_xy[:, 1].min() - y_pad)
    ymax = float(ref_xy[:, 1].max() + y_pad)
    return MotifGeometry(
        pair=selected_pair,
        path=path,
        plane_xy=proj.xy,
        plane_depth=proj.depth,
        box=(xmin, xmax, ymin, ymax),
    )


def _draw_adamantane_local_section(
    ax: plt.Axes,
    *,
    atoms: list[Atom],
    edges: list[Edge],
    motif: MotifGeometry,
) -> None:
    _setup_axis(ax)
    selected = set(motif.path)
    path_pairs = list(zip(motif.path[:-1], motif.path[1:]))

    def transform_xy(points: np.ndarray) -> np.ndarray:
        return -np.asarray(points)

    plane_xy = transform_xy(motif.plane_xy)
    xmin, xmax, ymin, ymax = motif.box
    box = (-xmax, -xmin, -ymax, -ymin)

    cell_polygons = {
        idx: transform_xy(np.asarray(_power_cell_polygon(idx, motif.plane_xy, motif.plane_depth, motif.box)))
        for idx in motif.path
    }

    for idx in motif.path:
        polygon = cell_polygons[idx]
        if polygon.size == 0:
            continue
        ax.add_patch(
            Polygon(
                polygon,
                closed=True,
                facecolor='white',
                edgecolor='none',
                zorder=0.1,
            )
        )

    drawn_segments: set[tuple] = set()
    for idx in motif.path:
        polygon = cell_polygons[idx]
        if polygon.size == 0:
            continue
        labels = _label_polygon_edges(idx, polygon, plane_xy, motif.plane_depth)
        for edge_idx, neighbor in enumerate(labels):
            if neighbor is None or neighbor not in selected:
                continue
            point_a = polygon[edge_idx]
            point_b = polygon[(edge_idx + 1) % len(polygon)]
            key = _segment_key(point_a, point_b, neighbor, idx)
            if key in drawn_segments:
                continue
            drawn_segments.add(key)
            ax.plot(
                [point_a[0], point_b[0]],
                [point_a[1], point_b[1]],
                color=SEPARATOR_TRACE,
                linestyle='-',
                linewidth=1.08,
                alpha=0.96,
                solid_capstyle='round',
                zorder=0.9,
            )

    for left, right in path_pairs:
        ax.plot(
            [plane_xy[left, 0], plane_xy[right, 0]],
            [plane_xy[left, 1], plane_xy[right, 1]],
            color=TRUE_EDGE,
            linewidth=0.92,
            alpha=0.58,
            zorder=1.5,
        )

    ax.plot(
        [plane_xy[motif.pair[0], 0], plane_xy[motif.pair[1], 0]],
        [plane_xy[motif.pair[0], 1], plane_xy[motif.pair[1], 1]],
        color=VISIBLE_EXTRA,
        linewidth=1.18,
        alpha=0.96,
        zorder=2.2,
    )

    in_plane = [motif.path[0], motif.path[1], motif.path[3], motif.path[4]]
    for idx in in_plane:
        atom = atoms[idx]
        style = ELEMENT_STYLE.get(atom.symbol, ELEMENT_STYLE['C'])
        ax.scatter(
            [plane_xy[idx, 0]],
            [plane_xy[idx, 1]],
            s=style['size'],
            facecolors=style['facecolor'],
            edgecolors=style['edgecolor'],
            linewidths=0.58,
            zorder=3.0,
        )

    middle = motif.path[2]
    ax.scatter(
        [plane_xy[middle, 0]],
        [plane_xy[middle, 1]],
        s=ELEMENT_STYLE['C']['size'],
        facecolors=ELEMENT_STYLE['C']['facecolor'],
        edgecolors=ELEMENT_STYLE['C']['edgecolor'],
        linewidths=0.58,
        alpha=0.35,
        zorder=2.8,
    )
    ax.text(
        plane_xy[middle, 0],
        plane_xy[middle, 1] - 0.170,
        'out of plane',
        fontsize=6.3,
        color='0.45',
        ha='center',
        va='bottom',
        zorder=2.6,
    )

    scale = 0.90
    x_center = 0.5 * (box[0] + box[1])
    y_center = 0.5 * (box[2] + box[3])
    x_half = 0.5 * (box[1] - box[0]) / scale
    y_half = 0.5 * (box[3] - box[2]) / scale
    ax.set_xlim(x_center - x_half, x_center + x_half)
    ax.set_ylim(y_center - y_half, y_center + y_half)
    _panel_label(ax, 'g')


def build_figure(
    *,
    structure_dir: Path,
    qtaim_dir: Path,
    voronoi_edges_csv: Path,
    powerfit_edges_csv: Path,
    output_pdf: Path,
    output_png: Path,
    methane_view: tuple[float, float, float],
    benzene_view: tuple[float, float, float],
    adamantane_view: tuple[float, float, float],
) -> None:
    atoms = {
        key: _read_xyz(structure_dir / f'{key}.xyz')
        for key in ['methane_occlusion', 'benzene_sym', 'benzene_broken', 'adamantane_sym']
    }
    qtaim_data = {
        key: _read_json(qtaim_dir / f'{key}.json')
        for key in ['methane_occlusion']
    }

    methane_separator_fraction = _methane_separator_fraction(
        qtaim_data['methane_occlusion']
    )
    vor_edges = _read_edges(voronoi_edges_csv)
    pow_edges = _read_edges(powerfit_edges_csv)

    methane_vor = _edges_for(vor_edges, 'methane_occlusion')
    benzene_sym_vor = _edges_for(vor_edges, 'benzene_sym')
    benzene_broken_vor = _edges_for(vor_edges, 'benzene_broken')
    benzene_sym_pow = _edges_for(pow_edges, 'benzene_sym')
    benzene_broken_pow = _edges_for(pow_edges, 'benzene_broken')
    adamantane_pow = _edges_for(pow_edges, 'adamantane_sym')

    adam_triangle = _adamantane_right_triangle(
        atoms['adamantane_sym'],
        adamantane_pow,
        view=adamantane_view,
    )
    adam_selected_pair = _adamantane_pair_for_local_motif(
        atoms['adamantane_sym'],
        adam_triangle,
        view=adamantane_view,
    )
    adam_motif = _adamantane_local_motif(
        atoms['adamantane_sym'],
        adamantane_pow,
        adam_selected_pair,
    )

    fig = plt.figure(figsize=(10.0, 5.2))
    grid = fig.add_gridspec(
        2,
        4,
        width_ratios=[0.88, 1.0, 1.0, 1.12],
        height_ratios=[1.0, 1.0],
        wspace=0.025,
        hspace=0.045,
    )

    ax_a = fig.add_subplot(grid[0, 0])
    _setup_axis(ax_a)
    methane_roles = _methane_roles(atoms['methane_occlusion'])
    methane_panel_a_pad = 0.24
    if methane_view == VIEW_DEFAULTS['methane']:
        methane_proj = _methane_projection(
            atoms['methane_occlusion'],
            split_degrees=-10.0,
        )
        _draw_edges(ax_a, methane_proj, methane_vor)
        _draw_atoms(ax_a, atoms['methane_occlusion'], methane_proj, size_scale=0.96)
        _set_panel_limits(ax_a, methane_proj.xy, pad=methane_panel_a_pad)
    else:
        methane_proj = _draw_molecule(
            ax_a,
            atoms['methane_occlusion'],
            methane_vor,
            view=methane_view,
            atom_size_scale=0.96,
        )
        _set_panel_limits(ax_a, methane_proj.xy, pad=methane_panel_a_pad)
    methane_target_bond_fraction = _methane_inplane_mean_bond_length(
        methane_proj,
        methane_roles,
    ) / float(_padded_span(methane_proj.xy, pad=methane_panel_a_pad)[0])
    _panel_label(ax_a, 'a')

    ax_b = fig.add_subplot(grid[1, 0])
    _draw_methane_slice(
        ax_b,
        atoms=atoms['methane_occlusion'],
        separator_fraction=methane_separator_fraction,
        target_bond_fraction=methane_target_bond_fraction,
    )

    benzene_raw_area_threshold = 1.0e-3
    ax_c = fig.add_subplot(grid[0, 1])
    _draw_benzene_overlay_panel(
        ax_c,
        atoms=atoms['benzene_sym'],
        vor_edges=benzene_sym_vor,
        pow_edges=benzene_sym_pow,
        view=benzene_view,
        panel_label='c',
        geometry_label='raw graph: sym.',
        min_raw_area=benzene_raw_area_threshold,
    )

    ax_d = fig.add_subplot(grid[0, 2])
    _draw_benzene_overlay_panel(
        ax_d,
        atoms=atoms['benzene_broken'],
        vor_edges=benzene_broken_vor,
        pow_edges=benzene_broken_pow,
        view=benzene_view,
        panel_label='d',
        geometry_label='raw graph: pert.',
        min_raw_area=benzene_raw_area_threshold,
    )

    ax_e = fig.add_subplot(grid[1, 1:3])
    _draw_benzene_visible_pair(
        ax_e,
        atoms_sym=atoms['benzene_sym'],
        atoms_broken=atoms['benzene_broken'],
        edges_sym=benzene_sym_pow,
        edges_broken=benzene_broken_pow,
        view=benzene_view,
    )

    ax_f = fig.add_subplot(grid[0, 3])
    _draw_adamantane_global_panel(
        ax_f,
        atoms=atoms['adamantane_sym'],
        edges=adamantane_pow,
        view=adamantane_view,
        triangle=adam_triangle,
    )

    ax_g = fig.add_subplot(grid[1, 3])
    _draw_adamantane_local_section(
        ax_g,
        atoms=atoms['adamantane_sym'],
        edges=adamantane_pow,
        motif=adam_motif,
    )

    handles = [
        Line2D([0], [0], color=TRUE_EDGE, linewidth=1.0, label='QTAIM-supported face'),
        Line2D([0], [0], color=RAW_EXTRA, linestyle=(0, (0.9, 1.4)), linewidth=1.0, label='raw-only extra face'),
        Line2D([0], [0], color=VISIBLE_EXTRA, linewidth=1.1, label='visible extra face'),
        Line2D([0], [0], color=SLIVER_EXTRA, linestyle=(0, (2.0, 1.4)), linewidth=1.15, label='visible C...C sliver'),
        Line2D([0], [0], color=SEPARATOR_TRACE, linewidth=1.2, label='separator trace'),
    ]
    fig.legend(
        handles=handles,
        loc='lower center',
        ncol=5,
        frameon=False,
        fontsize=7.2,
        bbox_to_anchor=(0.5, 0.005),
    )
    fig.subplots_adjust(left=0.015, right=0.985, top=0.985, bottom=0.095)

    save_figure_pair(
        fig,
        png_path=output_png,
        pdf_path=output_pdf,
        title=output_pdf.stem,
        png_dpi=300,
        bbox_inches='tight',
        pad_inches=0.015,
    )
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--structure-dir', type=Path, default=DEFAULT_STRUCTURE_DIR)
    parser.add_argument('--qtaim-dir', type=Path, default=DEFAULT_QTAIM_DIR)
    parser.add_argument('--voronoi-edges-csv', type=Path, default=DEFAULT_VORONOI_EDGES)
    parser.add_argument('--powerfit-edges-csv', type=Path, default=DEFAULT_POWERFIT_EDGES)
    parser.add_argument('--output-pdf', type=Path, default=DEFAULT_OUTPUT_PDF)
    parser.add_argument('--output-png', type=Path, default=DEFAULT_OUTPUT_PNG)
    parser.add_argument(
        '--view-methane',
        type=_parse_view,
        default=VIEW_DEFAULTS['methane'],
        help='Euler view rx,ry,rz in degrees',
    )
    parser.add_argument(
        '--view-benzene',
        type=_parse_view,
        default=VIEW_DEFAULTS['benzene'],
        help='Euler view rx,ry,rz in degrees',
    )
    parser.add_argument(
        '--view-adamantane',
        type=_parse_view,
        default=VIEW_DEFAULTS['adamantane'],
        help='Euler view rx,ry,rz in degrees',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_figure(
        structure_dir=args.structure_dir,
        qtaim_dir=args.qtaim_dir,
        voronoi_edges_csv=args.voronoi_edges_csv,
        powerfit_edges_csv=args.powerfit_edges_csv,
        output_pdf=args.output_pdf,
        output_png=args.output_png,
        methane_view=args.view_methane,
        benzene_view=args.view_benzene,
        adamantane_view=args.view_adamantane,
    )
    print(f'Wrote {args.output_pdf}')
    print(f'Wrote {args.output_png}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
