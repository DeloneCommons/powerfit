# Current manuscript figures

Seven vector PDFs are included by the current article. Their locations and
scientific roles are listed below; run commands from the repository root.

| Figure PDF | Placement | Source or construction |
|---|---|---|
| [figure_02_separators.pdf](figure_02_separators.pdf) | Section 2 | Exact two-site example: increasing the second weight moves the equal-power separator toward the first site. |
| [figure_03_cycle.pdf](figure_03_cycle.pdf) | Section 3.1 | Signed traversal of three observations on an abstract graph; the dashed return reverses an existing observation. |
| [figure_04_realization.pdf](figure_04_realization.pdf) | Section 4.1 | Exact four-site full-plane examples with an absent face, a face away from the connector point, and a strictly visible connector point. |
| [figure_05_workflow.pdf](figure_05_workflow.pdf) | Section 5 | One-pass fitting and optional observation-set refinement, with full-candidate matching and separate geometric diagnostics. |
| [figure_C_identifiability.pdf](figure_C_identifiability.pdf) | Section 6.1 | Frozen Experiment C: global and oracle componentwise weight alignment, and connected-graph frequency, at the largest tested site count. |
| [figure_G_mismatch.pdf](figure_G_mismatch.pdf) | Section 6.2 | Frozen Experiment G: target-RMSE improvement and whole-graph F1 change under structured separator mismatch. |
| [figure_E_bcp_projection.pdf](figure_E_bcp_projection.pdf) | Appendix E.2 | An analytic illustrative density with a gradient bond path, zero-flux boundary, and BCP projection onto the nuclear connector. |

Experiment H is represented by the E/H table and adverse-case discussion in
Section 6.3. Its candidate figure is excluded from the article and source bundle.

## Regenerate the figures

Install Python 3.10 or later with NumPy, Matplotlib, and pandas, then run:

```bash
python scripts/build_manuscript_figures.py
```

The wrapper uses the local frozen results. It runs no experiment, fitting
calculation, or molecular-data pipeline. Its default destination is
`manuscript/figures/`; to inspect output separately, use:

```bash
python scripts/build_manuscript_figures.py --output-dir build/figures
```

The implementation is split by source family:

| Generator | Figures | Inputs |
|---|---|---|
| [plot_theory_figures.py](../../scripts/plot_theory_figures.py) | Separators, cycle, realization, workflow | Explicit geometric constructions and workflow routes; no numerical archive. |
| [plot_editorial_figures.py](../../scripts/plot_editorial_figures.py) | C and BCP projection | Frozen C runs, archived summaries and metadata; analytic density for the BCP schematic. |
| [plot_experiment_g.py](../../scripts/plot_experiment_g.py) | G | Frozen paired Experiment G results. |

Use the wrapper as the public entry point. The theory generator also supports
`--figure separators`, `cycle`, `realization`, or `workflow` for targeted
construction work. Only the seven PDFs are article dependencies; editable SVGs
produced by some generators are supplementary outputs.

## Data and interpretation checks

Figure C reads `results/missing_data_manuscript/runs.csv`,
`manuscript_analysis/summary.csv`, and `metadata.json` from that result tree.
The generator verifies the full 2,470-run, 247-group sweep against the frozen
summary before selecting the two `n=128` profiles. Each of the 19 retention
settings in each dimension uses ten runs. The horizontal coordinate is the
requested retention fraction; different settings are independent samples.
The `1e-16` display floor is applied after the median of per-run RMSEs.
Componentwise alignment uses the known generating weights as an evaluation
oracle and does not infer missing component offsets.

Figure G uses 2,160 paired runs from `results/model_mismatch/`. It distinguishes
agreement with the imposed fitting targets from recovery of the entire
generating adjacency graph. Markers show arithmetic means, and bars show the
middle 50% of observations rather than confidence intervals. Different mismatch
amplitudes use independent instances.

The BCP drawing is an exact conceptual density construction in arbitrary
illustrative units. Its curved boundary and gradient paths are not measured
molecular surfaces, and the connector-normal plane through the BCP does not
assert a finite realized power face. The workflow figure distinguishes the
full candidate collection sent to matching from the active subset used in a
refined fit. The requested-image realization flag drives the optional updates;
residuals and connector diagnostics do not.

The four-site figure represents full-plane cells. The drawing window is a
viewport, and the clearance bracket measures the connector-to-boundary distance
within the face. The signed-cycle illustration is an observation graph, not a
geometric diagram or a difference-constraint graph. The focused tests preserve
these distinctions.

## Verification and reproducibility

```bash
python scripts/check_manuscript_figures.py
python -m unittest discover -s tests -v
```

The figure checker uses Poppler's PDF inspection and rendering tools
(`poppler-utils` on Debian/Ubuntu), generates temporary outputs, checks
repeatability within one environment, and compares rendered output with the committed PDFs. Explicit
metadata and deterministic export settings make repeated production in the
same environment reproducible. Different Matplotlib, font, or rendering
versions can change the PDF bytes, so cross-environment byte equality with
the committed PDFs is not promised. On restricted systems, set `MPLCONFIGDIR`
to a writable cache directory.

The PDF checks reject Type 3 fonts and require embedded fonts except for one
approved standard-font use: the workflow figure's heading uses PDF Base14
`Times-Roman` without embedding. That exception is preserved when the figure is
included in the article. All other figure and article fonts are checked for
embedding.

The article build, `bash scripts/build_manuscript_pdfs.sh`, compiles the
committed figures without regenerating them. Historical figure helpers write to
`build/legacy/figures/` and are outside the current article build; their archived
source and result records remain available.
