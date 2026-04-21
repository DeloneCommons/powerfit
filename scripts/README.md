# Scripts

Utility scripts for the frozen paper repository.

## Read these scripts in this order

- `check_repo_consistency.py` — fast audit for broken markdown links, leaked
  machine-specific absolute paths, missing documented runtime requirements,
  bundled-binary digest mismatches, and flat-bundle dependency collisions.
- `rerun_paper_results.sh` — rerun Experiments A--H, rerun the committed-data
  Experiment J analyses, call the canonical manuscript build, and finish with
  the repository consistency audit.
- `capture_environment_snapshot.py` — one-time release helper that records the
  exact Python lock file and system note under `environments/`.
- `build_manuscript_tables.py` — regenerate the manuscript-side table fragments
  that are actually used by `manuscript/manuscript.tex`.
- `build_manuscript_figures.py` — regenerate manuscript-facing figure files from
  source scripts and archived result files.
- `_figure_io.py` — deterministic Matplotlib save helper used by the
  manuscript-facing figure generators and by the current Python plot writers
  under `experiments/analysis/` and `scripts/qtaim/`.
- `check_figure_binary_constancy.py` — rerun a representative subset of the
  figure generators twice in a throwaway directory and compare output hashes.
  This is intentionally heavier than the fast repo audit and is meant for
  release-time or post-refactor verification in the locked environment.
- `make_submission_bundle.py` — create the flat journal-submission source bundle
  from `manuscript/`, preferring PDF figures when both PDF and PNG copies exist.
- `build_manuscript_pdfs.sh` — refresh manuscript tables and figures, build the
  local `manuscript/manuscript.pdf`, rebuild the tracked `submission/flat/`
  source bundle, optionally build the ignored verification PDF
  `submission/flat/manuscript.pdf`, clean auxiliary LaTeX byproducts, and fail
  immediately if `latexmk` or `bibtex` is unavailable on `PATH`.
- `qtaim/README.md` — optional molecular-data regeneration helpers; not needed
  for ordinary manuscript review or for rerunning the already archived results.

## Manuscript table source map

Run the targeted table-only refresh with:

```bash
python scripts/build_manuscript_tables.py
```

For targeted edits, the same script contains one function per generated table:

| Manuscript file | Generator function | Main archived inputs |
|---|---|---|
| `manuscript/tables/table_A_exact_recovery.tex` | `table_a()` | `results/exact_recovery/` |
| `manuscript/tables/table_B_noise_response.tex` | `table_b()` | `results/noise_robustness/` |
| `manuscript/tables/table_D_infeasible_constraints.tex` | `table_d()` | `results/infeasible/` |
| `manuscript/tables/table_E_active_set.tex` | `table_e()` | `results/active_set/` |
| `manuscript/tables/table_F_periodic.tex` | `table_f()` | `results/periodic/` |
| `manuscript/tables/table_G_model_mismatch.tex` | `table_g()` | `results/model_mismatch/` |
| `manuscript/tables/table_H_supergraph_mismatch.tex` | `table_h()` | `results/supergraph_mismatch/` |
| `manuscript/tables/table_J1_dataset_audit.tex` | `table_j1_dataset_audit()` | `results/qtaim_main/J1_dataset_audit/` |
| `manuscript/tables/table_J23_reference_summary.tex` | `table_j23_reference_summary()` | `results/qtaim_main/J2_true_support_ladder/`, `results/qtaim_main/J3_candidate_recovery_refresh/` |
| `manuscript/tables/table_J4_local_validation.tex` | `table_j4_local_validation()` | `results/qtaim_main/J4_local_diagnostic_validation/` |
| `manuscript/tables/table_J4_clearance_ranking.tex` | `table_j4_clearance_ranking()` | `results/qtaim_main/J4_mask_transfer_refresh/` |

The compact synthetic main-text table `table_synthetic_summary.tex` is
hand-maintained because it is a narrative summary rather than a direct aggregate
export.

## Manuscript figure source map

Run the targeted figure-only refresh with:

```bash
python scripts/build_manuscript_figures.py
```

Targeted figure rebuilds are:

| Manuscript file | Generator / source | Notes |
|---|---|---|
| `manuscript/figures/figure_powerfit_workflow_overview.{pdf,png}` | `python scripts/make_workflow_schematic.py --figure-path manuscript/figures/figure_powerfit_workflow_overview.png` | Introductory workflow schematic. |
| `manuscript/figures/figure_C_missing_data_composite.{pdf,png}` | `python experiments/analysis/plot_missing_data_manuscript.py --figure-path manuscript/figures/figure_C_missing_data_composite.png` | Experiment C missing-data transition. |
| `manuscript/figures/figure_J4_geometry_cases.{pdf,png}` | `python scripts/make_j4_geometry_cases.py` | Geometry-first showcase drawn from `data/qtaim_showcase/structures/` and `results/qtaim_showcase_voronoi/`. Use `--view-methane`, `--view-benzene`, and `--view-adamantane` to tune the borderless 3D projections. |
| `manuscript/figures/figure_J4_mask_transfer.{pdf,png}` | `python scripts/make_j4_mask_transfer_figure.py` | One-panel precision--recall transition from `results/qtaim_main/J4_mask_transfer_refresh/`; precision is the horizontal axis and both legends are kept outside the data pane. |

For the canonical end-to-end manuscript rebuild, use `bash scripts/build_manuscript_pdfs.sh`; the targeted table and figure refreshers above are for asset-specific edits.

The manuscript-facing figure generators listed above save both PNG and PDF
outputs through the deterministic helper in `_figure_io.py`. In the same locked
Python environment recorded under `environments/`, those paired files are
expected to be byte-identical across rebuilds. The guarantee is intentionally
narrow: it covers the generated figure assets, not the final LaTeX-built
`manuscript/manuscript.pdf` or `submission/flat/manuscript.pdf`. To verify that
property without touching tracked outputs, run:

```bash
python scripts/check_figure_binary_constancy.py
```

Use `--suite manuscript` for a faster check limited to the four manuscript
figure generators.

Legacy helper scripts and non-current result branches are intentionally not
part of the main build path in this released paper artifact.
