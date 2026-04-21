"""Shared proatomic pair-law utilities for local separator predictions.

The helpers in this module load aggregated radial-density tables, build smooth
interpolants, and evaluate the two-atom promolecule minimum used as the local
separator baseline in later QTAIM analyses.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import minimize_scalar


@dataclass(frozen=True)
class PairLawRecord:
    element_i: str
    element_j: str
    distance_angstrom: float
    x_from_i_angstrom: float
    fraction_from_i: float
    rho_min: float
    valid_interior_minimum: bool


@dataclass(frozen=True)
class PairLawPrediction:
    element_i: str
    element_j: str
    distance_angstrom: float
    x_from_i_angstrom: float
    fraction_from_i: float
    rho_min: float | None
    source: str


class RadialDensityTable:
    def __init__(self, r_angstrom: np.ndarray, density_by_element: dict[str, np.ndarray]):
        if r_angstrom.ndim != 1:
            raise ValueError('r_angstrom must be one-dimensional')
        if len(r_angstrom) < 2:
            raise ValueError('At least two radial grid points are required')
        self.r_angstrom = np.asarray(r_angstrom, dtype=float)
        self.density_by_element = {k: np.asarray(v, dtype=float) for k, v in density_by_element.items()}
        self.elements = sorted(self.density_by_element)
        self._interpolators = {
            element: PchipInterpolator(self.r_angstrom, values, extrapolate=False)
            for element, values in self.density_by_element.items()
        }

    def rho(self, element: str, x_angstrom: float | np.ndarray) -> np.ndarray:
        if element not in self._interpolators:
            raise KeyError(f'Unknown element {element!r}')
        x = np.asarray(x_angstrom, dtype=float)
        y = self._interpolators[element](x)
        finite = np.isfinite(y) & (x >= float(self.r_angstrom[0])) & (x <= float(self.r_angstrom[-1]))
        return np.where(finite, y, 0.0)

    def rho_scalar(self, element: str, x_angstrom: float) -> float:
        return float(self.rho(element, x_angstrom))

    def promolecule_density(self, element_i: str, element_j: str, distance_angstrom: float, x_from_i_angstrom: float) -> float:
        return self.rho_scalar(element_i, x_from_i_angstrom) + self.rho_scalar(element_j, distance_angstrom - x_from_i_angstrom)

    def minimum_between_atoms(
        self,
        element_i: str,
        element_j: str,
        distance_angstrom: float,
        *,
        xatol: float = 1.0e-6,
    ) -> PairLawRecord:
        if distance_angstrom <= 0.0:
            raise ValueError('distance_angstrom must be positive')
        if element_i == element_j:
            midpoint = 0.5 * distance_angstrom
            return PairLawRecord(
                element_i=element_i,
                element_j=element_j,
                distance_angstrom=float(distance_angstrom),
                x_from_i_angstrom=midpoint,
                fraction_from_i=0.5,
                rho_min=self.promolecule_density(element_i, element_j, distance_angstrom, midpoint),
                valid_interior_minimum=True,
            )

        def objective(x: float) -> float:
            return self.promolecule_density(element_i, element_j, distance_angstrom, x)

        result = minimize_scalar(
            objective,
            bounds=(0.0, float(distance_angstrom)),
            method='bounded',
            options={'xatol': float(xatol), 'maxiter': 500},
        )
        x_value = float(result.x)
        tol = max(1.0e-9, 10.0 * xatol)
        valid_interior = (x_value > tol) and ((distance_angstrom - x_value) > tol)
        return PairLawRecord(
            element_i=element_i,
            element_j=element_j,
            distance_angstrom=float(distance_angstrom),
            x_from_i_angstrom=x_value,
            fraction_from_i=(x_value / float(distance_angstrom)),
            rho_min=float(result.fun),
            valid_interior_minimum=valid_interior,
        )


class PairLawLookup:
    def __init__(self, rows: list[PairLawRecord]):
        self.rows = rows
        by_pair: dict[tuple[str, str], list[PairLawRecord]] = {}
        for row in rows:
            by_pair.setdefault((row.element_i, row.element_j), []).append(row)
        self.by_pair: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
        for pair_key, pair_rows in by_pair.items():
            pair_rows = sorted(pair_rows, key=lambda row: row.distance_angstrom)
            distances = np.array([row.distance_angstrom for row in pair_rows], dtype=float)
            x_values = np.array([row.x_from_i_angstrom for row in pair_rows], dtype=float)
            fractions = np.array([row.fraction_from_i for row in pair_rows], dtype=float)
            rho_min = np.array([row.rho_min for row in pair_rows], dtype=float)
            self.by_pair[pair_key] = (distances, x_values, fractions, rho_min)

    def predict(self, element_i: str, element_j: str, distance_angstrom: float) -> PairLawPrediction:
        key = (element_i, element_j)
        if key not in self.by_pair:
            raise KeyError(f'No pair-law data available for ordered pair {key!r}')
        distances, x_values, fractions, rho_min = self.by_pair[key]
        if distance_angstrom < float(distances[0]) or distance_angstrom > float(distances[-1]):
            raise ValueError(
                f'Distance {distance_angstrom:.6f} Å is outside lookup range '
                f'[{distances[0]:.6f}, {distances[-1]:.6f}] Å for pair {element_i}-{element_j}'
            )
        x_value = float(np.interp(distance_angstrom, distances, x_values))
        fraction = float(np.interp(distance_angstrom, distances, fractions))
        rho_value = float(np.interp(distance_angstrom, distances, rho_min))
        return PairLawPrediction(
            element_i=element_i,
            element_j=element_j,
            distance_angstrom=float(distance_angstrom),
            x_from_i_angstrom=x_value,
            fraction_from_i=fraction,
            rho_min=rho_value,
            source='lookup_linear_interp',
        )



def load_radial_density_table(csv_path: Path) -> RadialDensityTable:
    with csv_path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if not fieldnames or fieldnames[0] != 'r_angstrom':
            raise ValueError('Expected first column r_angstrom in radial-density CSV')
        elements = fieldnames[1:]
        r_values: list[float] = []
        density_by_element: dict[str, list[float]] = {element: [] for element in elements}
        for row in reader:
            if not any((value or '').strip() for value in row.values()):
                continue
            r_values.append(float(row['r_angstrom']))
            for element in elements:
                density_by_element[element].append(float(row[element]))
    return RadialDensityTable(
        r_angstrom=np.array(r_values, dtype=float),
        density_by_element={element: np.array(values, dtype=float) for element, values in density_by_element.items()},
    )



def write_lookup_csv(rows: Iterable[PairLawRecord], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                'element_i',
                'element_j',
                'distance_angstrom',
                'x_from_i_angstrom',
                'fraction_from_i',
                'rho_min',
                'valid_interior_minimum',
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    'element_i': row.element_i,
                    'element_j': row.element_j,
                    'distance_angstrom': f'{row.distance_angstrom:.10f}',
                    'x_from_i_angstrom': f'{row.x_from_i_angstrom:.10f}',
                    'fraction_from_i': f'{row.fraction_from_i:.10f}',
                    'rho_min': f'{row.rho_min:.12e}',
                    'valid_interior_minimum': 'true' if row.valid_interior_minimum else 'false',
                }
            )



def load_lookup_csv(csv_path: Path) -> PairLawLookup:
    rows: list[PairLawRecord] = []
    with csv_path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        required = {
            'element_i',
            'element_j',
            'distance_angstrom',
            'x_from_i_angstrom',
            'fraction_from_i',
            'rho_min',
            'valid_interior_minimum',
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError('Lookup CSV missing required columns: ' + ', '.join(sorted(missing)))
        for row in reader:
            if not any((value or '').strip() for value in row.values()):
                continue
            rows.append(
                PairLawRecord(
                    element_i=row['element_i'].strip(),
                    element_j=row['element_j'].strip(),
                    distance_angstrom=float(row['distance_angstrom']),
                    x_from_i_angstrom=float(row['x_from_i_angstrom']),
                    fraction_from_i=float(row['fraction_from_i']),
                    rho_min=float(row['rho_min']),
                    valid_interior_minimum=(row['valid_interior_minimum'].strip().lower() in {'1', 'true', 'yes'}),
                )
            )
    if not rows:
        raise ValueError(f'No lookup rows found in {csv_path}')
    return PairLawLookup(rows)



def write_metadata_json(payload: dict, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write('\n')
