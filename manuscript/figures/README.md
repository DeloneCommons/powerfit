# Figures

Publication figures used by `manuscript.tex` live here. Run
`python scripts/build_manuscript_figures.py` from the repo root for a targeted
figure-only refresh after figure-script changes. For the canonical end-to-end
manuscript build, use `bash scripts/build_manuscript_pdfs.sh`.

## Main-text figures currently wired in the manuscript

| Figure file | How to regenerate it | Main inputs |
|---|---|---|
| `figure_powerfit_workflow_overview.{pdf,png}` | `python scripts/make_workflow_schematic.py --figure-path manuscript/figures/figure_powerfit_workflow_overview.png` | self-contained schematic script |
| `figure_C_missing_data_composite.{pdf,png}` | `python experiments/analysis/plot_missing_data_manuscript.py --figure-path manuscript/figures/figure_C_missing_data_composite.png` | `results/missing_data_manuscript/` |
| `figure_J4_geometry_cases.{pdf,png}` | `python scripts/make_j4_geometry_cases.py` | `data/qtaim_showcase/structures/`, `results/qtaim_showcase_voronoi/` |
| `figure_J4_mask_transfer.{pdf,png}` | `python scripts/make_j4_mask_transfer_figure.py` | `results/qtaim_main/J4_mask_transfer_refresh/mask_summary.csv`, `clearance_sweep.csv` |

The wrapper script performs all of the steps above in the right order. The J4
geometry script accepts `--view-methane`, `--view-benzene`, and
`--view-adamantane` options of the form `rx,ry,rz` in degrees, which makes it
safe to tune the borderless molecule projections without editing the script.

Superseded manuscript-side figures were removed from this directory. Their
underlying result roots are either still available under `results/` or are no
longer part of the released paper artifact.

The manuscript-facing figure generators now save both PNG and PDF outputs
through a deterministic helper. In the same locked Python environment recorded
under `environments/`, the paired files are expected to be byte-identical
across rebuilds. Outside that locked environment, visual equivalence remains
the relevant check. This guarantee covers the figure assets in this directory,
not the final LaTeX-built manuscript PDF. To verify the byte-stability claim
without modifying tracked files, run `python
scripts/check_figure_binary_constancy.py --suite manuscript` from the repo
root.
