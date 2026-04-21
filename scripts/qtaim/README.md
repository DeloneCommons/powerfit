# QTAIM helper scripts

This directory contains the project-specific helpers used to build both the
small fixed QTAIM showcase and the larger molecule benchmark.

For the ordinary paper-side rerun from committed data, use
`../rerun_paper_results.sh` from the repo root. The scripts documented here are
mainly for targeted Experiment J analyses or for the optional full molecular
regeneration path.

The workflow is split into the following stages.

## Proatomic reference branch

0. `run_pyscf_atomic_singlepoint.py`
   - reads `data/proatomic/atom_manifest.csv` or a compatible manifest;
   - builds isolated-atom PySCF single points for proatomic references;
   - writes Molden files for the listed atoms;
   - writes one global CSV summary and one global error log.

0a. `run_multiwfn_radial_density.py`
   - reads the same proatomic manifest;
   - runs Multiwfn radial analysis (`200 -> 5`) for each Molden file;
   - exports both `RDF.txt` and `sphavgval.txt` into `data/proatomic/radial/raw/<species>/`;
   - aggregates the raw outputs into `data/proatomic/radial/rdf_grid.csv` and
     `data/proatomic/radial/radial_density_grid.csv`;
   - writes a metadata JSON recording the exact protocol and units.

0b. `build_proatomic_separator_lookup.py`
   - reads the aggregated radial-density grid;
   - tabulates the promolecule-minimum separator law on a fixed distance grid;
   - writes `data/proatomic/pairlaw/separator_lookup.csv` and metadata JSON.

0c. `analyze_qtaim_proatomic.py`
   - reads a QTAIM manifest plus the frozen pair-law lookup;
   - projects BCP locations to atom-atom connectors;
   - compares midpoint and proatomic local-law predictions;
   - writes edge-, molecule-, pair-type-, and threshold-level summaries.

## Molecule-side dataset branch

1. `select_pubchem_main.py`
   - performs the two PubChem searches used for the larger benchmark;
   - applies exact local RDKit filtering and connectivity-SMILES de-duplication;
   - writes `systems.csv`, `systems_reserve.csv`, and audit logs into `data/qtaim_main/`;
   - optionally downloads PubChem SDF files for the selected/reserve molecules.

2. `run_pyscf_geomopt.py`
   - reads a manifest CSV;
   - resolves all relative paths against the manifest location;
   - uses row-specific `charge` and `multiplicity`;
   - builds a starting geometry from `smiles` with an RDKit ETKDG conformer
     search, MMFF/UFF ranking, and lowest-energy conformer selection;
   - optionally bypasses RDKit and uses `input_xyz_path` when a manual starting
     geometry is provided for a row;
   - writes the optimized geometry to `xyz_path`;
   - writes one global CSV summary and one global error log;
   - does **not** emit per-system PySCF log files by default.

3. `run_pyscf_singlepoint.py`
   - reads the same manifest CSV or a downstream manifest using canonical
     optimized geometries;
   - resolves `xyz_path` and `molden_path` relative to the manifest if needed;
   - uses row-specific `charge` and `multiplicity`;
   - writes only the requested Molden files;
   - writes one global CSV summary and one global error log;
   - does **not** emit per-system PySCF log files by default.

4. `run_multiwfn_topology.py`
   - reads the same manifest CSV;
   - uses `molden_path` as input and `json_path` as output;
   - runs Multiwfn topology analysis with CP searches 2–5, then path generation 8,
     then prints the final summary with option 0;
   - stores one raw log directory per system under `multiwfn_raw/`;
   - parses the final CP table into compact JSON records.

5. `compare_qtaim_voronoi.py`
   - reads parsed QTAIM JSON records;
   - compares the QTAIM BCP support graph against ordinary Voronoi and one-shot powerfit;
   - writes CSV summaries for graph agreement, projection diagnostics, and symmetry-breaking differences.

6. `analyze_qtaim_dataset_audit.py`
   - runs J1, the molecular-topology audit;
   - quantifies RCP/CCP prevalence, nonbonded BCP-supported edges, graph-distance bins, and BCP off-axis projection quality;
   - is safe to run against `data/qtaim_main/systems_final.csv` before all `json_path` files exist, because missing rows are skipped by default.

7. `analyze_qtaim_true_support_ladder.py`
   - runs J2, the separator ladder on true QTAIM support;
   - compares midpoint, frozen proatomic local law, proatomic + one-shot powerfit, and the support-conditioned QTAIM-target ceiling;
   - writes edge-, molecule-, subset-, and pair-type summaries for the selected manifest subset.

8. `analyze_qtaim_candidate_recovery.py`
   - runs J3, the end-to-end recovery experiment from generic cutoff supergraphs;
   - reports candidate inflation / coverage, recovered support precision-recall, conditional recall, and separator RMSE on recovered true edges.

9. `local_support.py`
   - implements the manuscript's row-local connector-visibility quantities without relying on tessellation objects;
   - exposes the connector parameter, competitor slacks, visibility margin, unclipped clearance, and padded-box clearance.

10. `validate_local_support_diagnostics.py`
   - runs J4a, the theorem-to-code validation stage;
   - compares the analytic clipped connector-visibility and clearance formulas against the tessellation-derived J4 face diagnostics;
   - writes the compact validation summary used directly by the manuscript.

11. `analyze_qtaim_mask_transfer.py`
   - runs J4b, the quantitative archive-conditioned mask-transfer experiment on the main molecular benchmark;
   - computes a plain-Voronoi baseline, reads the J3 recovered powerfit graph at the reference cutoff, and evaluates the same realized-face mask ladder on both;
   - reports raw / visible / numerical-cleanup graph agreement, a clearance-threshold sweep, and visible-face clearance distributions for QTAIM-supported versus surplus faces on bonded and nonbonded subsets;
   - when available, propagates the analytic connector-visibility diagnostics emitted by J3 and computes the same diagnostics for the Voronoi baseline directly from the fitted weights and the padded box.

12. `analyze_qtaim_box_margin_sensitivity.py`
   - runs J4d, the padded-box robustness summary for the archive-conditioned J4b diagnostics;
   - compares a collection of precomputed J4b runs produced at different box margins;
   - reports visible-graph F1, clearance-threshold F1, clearance AP, short-distance AP, and the fraction of visible faces whose clearance is provably unaffected by clipping.

## Current status pointers

For the current manuscript-facing Experiment J branch, read:

- `results/qtaim_main/STATUS.md` for the refreshed full-benchmark summary;
- `results/qtaim_main/README.md` for the stage-by-stage result guide;
- `data/qtaim_main/systems_final.csv`, `systems_final_acyclic.csv`, and `systems_final_cyclic.csv` for the frozen benchmark manifests.

## Recommended manifest convention

For a reusable main dataset, the cleanest column pattern is:

- `smiles` — primary source for RDKit starting-geometry generation
- `input_xyz_path` — optional manual override for rows where RDKit is not
  appropriate
- `xyz_path` — canonical optimized geometry used downstream
- `molden_path` — Molden output from the single-point stage
- `json_path` — parsed QTAIM / CP JSON from Multiwfn
- `charge`
- `multiplicity`

The showcase manifest only needs the downstream columns because its committed
XYZ files are already fixed analysis geometries.

## Deterministic figure-output note

The current QTAIM analysis plot writers that emit PDF/PNG figures route output through `../_figure_io.py`. In the same locked Python environment recorded under `../environments/`, those generated figure pairs are expected to be byte-identical across rebuilds. Outside that locked environment, visual equivalence remains the relevant check. The dedicated verification helper `python scripts/check_figure_binary_constancy.py` uses `analyze_qtaim_dataset_audit.py` as the representative QTAIM-side case in its default suite.

## Progress reporting

Several of the longer-running scripts now emit console progress messages and,
when `tqdm` is available, progress bars. These are intentionally console-only
changes: they do not alter any CSV, JSON, XYZ, Molden, or raw Multiwfn file
artifacts. Use `--no-progress` to disable them.

## Examples

Generate isolated-atom Molden files:

```bash
python scripts/qtaim/run_pyscf_atomic_singlepoint.py \
  data/proatomic/atom_manifest.csv \
  --nproc 4
```

Build the isolated-atom radial tables:

```bash
python scripts/qtaim/run_multiwfn_radial_density.py \
  data/proatomic/atom_manifest.csv \
  --nproc 4
```

Build the proatomic pair-law lookup:

```bash
python scripts/qtaim/build_proatomic_separator_lookup.py
```

Refresh the synchronized J3/J4 molecular analyses and summarize the padded-box sweep:

```bash
python scripts/qtaim/analyze_qtaim_candidate_recovery.py \
  data/qtaim_main/systems_final.csv \
  --output-dir results/qtaim_main/J3_candidate_recovery_refresh

python scripts/qtaim/analyze_qtaim_mask_transfer.py \
  data/qtaim_main/systems_final.csv \
  --j3-selected-csv results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv \
  --output-dir results/qtaim_main/J4_mask_transfer_refresh

python scripts/qtaim/validate_local_support_diagnostics.py \
  --edge-level-csv results/qtaim_main/J4_mask_transfer_refresh/edge_level.csv \
  --output-dir results/qtaim_main/J4_local_diagnostic_validation

python scripts/qtaim/analyze_qtaim_box_margin_sensitivity.py \
  results/qtaim_main/J4_mask_transfer_margin3_refresh \
  results/qtaim_main/J4_mask_transfer_refresh \
  results/qtaim_main/J4_mask_transfer_margin7_refresh \
  results/qtaim_main/J4_mask_transfer_margin10_refresh \
  --labels 3A 5A 7A 10A \
  --output-dir results/qtaim_main/J4_box_margin_summary_refresh
```

Build a random PubChem-backed main manifest:

```bash
python scripts/qtaim/select_pubchem_main.py \
  --output-dir data/qtaim_main \
  --email you@example.org
```

Geometry optimization from a manifest that primarily uses SMILES:

```bash
python scripts/qtaim/run_pyscf_geomopt.py \
  data/qtaim_main/systems.csv \
  --nproc 4
```

Generate Molden files:

```bash
python scripts/qtaim/run_pyscf_singlepoint.py \
  data/qtaim_showcase/systems.csv \
  --nproc 4
```

Run Multiwfn and parse CP data:

```bash
python scripts/qtaim/run_multiwfn_topology.py \
  data/qtaim_showcase/systems.csv \
  --nproc 4 \
  --overwrite
```

The Multiwfn runners default to the bundled `external_software/Multiwfn_noGUI`
binary and set `Multiwfnpath` to the same directory so that the bundled
`settings.ini` is used automatically.

## Current scope

These scripts currently support:

- the molecule-side SMILES/manual-XYZ → optimized XYZ → Molden → CP-json pipeline;
- the proatomic reference branch through radial-density aggregation, pair-law
  lookup construction, and QTAIM-vs-proatomic separator analysis.

IAS surface export and IAS-derived geometric summaries are not part of the
frozen Experiment J workflow and are no longer kept in the committed repo.

## Experiment J freeze

The current molecular-benchmark defaults are frozen in
`experiments/configs/qtaim_molecular.yaml`, and the experiment plan is tracked in
`experiments/registry/J_qtaim_molecular.md`. The intended ladder is:

- **J1** dataset/topology audit,
- **J2** true-support separator ladder,
- **J3** candidate-supergraph recovery,
- **J4a** local theorem-to-code validation,
- **J4b** quantitative mask transfer,
- **J4c** curated representative-geometry panel,
- **J4d** padded-box robustness summary.

J3 is the fixed-denominator recovery stage against the common 3975-edge QTAIM
graph. J4b and J4d instead score diagnostics within each model's realized-face
archive.

The current archive includes the frozen J1--J4 scripts and the committed
full-benchmark outputs under `results/qtaim_main/`, with the reviewer-facing
read order explained in `results/qtaim_main/README.md`.


## Post-rerun manuscript refresh

After rerunning frozen J1--J4, refresh the manuscript-facing artifacts with the
canonical manuscript build:

```bash
bash scripts/build_manuscript_pdfs.sh
```
