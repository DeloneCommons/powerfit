# Experiment J4b: mask transfer

- Manifest: `data/qtaim_main/systems_final.csv`
- Reference J3 cutoff: **5.0 A**
- Processed molecules: **100**
- Skipped rows: **0**
- Numerical sliver cleanup: visible face with clearance <= **1.0e-04 A** (clearance-only safeguard)
- J3 reports fixed-denominator support recovery against the common 3975-edge QTAIM graph. J4b instead evaluates realized-face diagnostics within each model's realized-face archive.
- Archive-conditioned truth pool: Voronoi **3973** overall / **270** nonbonded QTAIM-supported realized faces; recovered powerfit **3975** overall / **272** nonbonded.

## Overall archive-conditioned mask ladder

### voronoi

- raw: precision / recall / F1 = **0.206 / 1.000 / 0.342**, extra-edge rate **0.794**.
- visible: precision / recall / F1 = **0.663 / 0.997 / 0.796**, extra-edge rate **0.337**.
- visible + numerical cleanup: precision / recall / F1 = **0.663 / 0.997 / 0.797**, extra-edge rate **0.337**.

### recovered_powerfit

- raw: precision / recall / F1 = **0.204 / 1.000 / 0.339**, extra-edge rate **0.796**.
- visible: precision / recall / F1 = **0.697 / 0.999 / 0.821**, extra-edge rate **0.303**.
- visible + numerical cleanup: precision / recall / F1 = **0.697 / 0.999 / 0.821**, extra-edge rate **0.303**.

## Bonded vs nonbonded after the visible numerical cleanup

- voronoi: bonded F1 **1.000**, nonbonded F1 **0.203**.
- recovered_powerfit: bonded F1 **1.000**, nonbonded F1 **0.238**.

## Numerical-cleanup note

- Near-zero-clearance faces removed on the full frozen benchmark: Voronoi **1**, recovered powerfit **2**.
- This safeguard is intentionally minimal. Face area is no longer part of the broad-dataset filtering story.

## Clearance sweep takeaways

- voronoi, all: best F1 on the tested sweep is **0.970** at clearance >= **0.60 A** (precision **0.961**, recall **0.979**).
- recovered_powerfit, all: best F1 on the tested sweep is **0.981** at clearance >= **0.60 A** (precision **0.988**, recall **0.975**).
- voronoi, nonbonded: best F1 on the tested sweep is **0.623** at clearance >= **0.60 A** (precision **0.555**, recall **0.711**).
- recovered_powerfit, nonbonded: best F1 on the tested sweep is **0.742** at clearance >= **0.50 A** (precision **0.658**, recall **0.849**).
- voronoi, bonded: best F1 on the tested sweep is **1.000** at clearance >= **0.00 A** (precision **0.999**, recall **1.000**).
- recovered_powerfit, bonded: best F1 on the tested sweep is **1.000** at clearance >= **0.00 A** (precision **0.999**, recall **1.000**).

## Same-threshold comparison at 0.50 A (archive-conditioned)

- all: Voronoi F1 **0.951** vs recovered-powerfit F1 **0.979**; precision **0.920 -> 0.970**, recall **0.985 -> 0.988**.
- nonbonded: Voronoi F1 **0.524** vs recovered-powerfit F1 **0.742**; precision **0.390 -> 0.658**, recall **0.796 -> 0.849**.
- heteronuclear: Voronoi F1 **0.976** vs recovered-powerfit F1 **0.989**; precision **0.974 -> 0.993**, recall **0.978 -> 0.985**.

## Visible-face clearance distributions

- The sweep remains the primary transfer diagnostic. These distributions explain why it works by comparing visible realized faces split into QTAIM-supported versus surplus classes.

### bonded

- voronoi: QTAIM-supported median clearance **0.834 A** (p05/p95 **0.729 / 1.126**), extra-face median **0.973 A** (p05/p95 **0.972 / 0.974**).
- recovered_powerfit: QTAIM-supported median clearance **1.045 A** (p05/p95 **0.905 / 1.235**), extra-face median **1.126 A** (p05/p95 **1.120 / 1.132**).

### nonbonded

- voronoi: QTAIM-supported median clearance **0.798 A** (p05/p95 **0.352 / 0.946**), extra-face median **0.360 A** (p05/p95 **0.012 / 0.677**).
- recovered_powerfit: QTAIM-supported median clearance **0.678 A** (p05/p95 **0.219 / 0.861**), extra-face median **0.228 A** (p05/p95 **0.013 / 0.536**).

## Interpretation

- J3 is the fixed-denominator recovery stage; J4b is the conditional realized-face diagnostic stage.
- Visibility is the methane-derived transfer mask: it removes screened connector-nonvisible faces.
- The near-zero-clearance cleanup is only a numerical safeguard. It is not a chemistry-specific filter and does not use face area.
- The clearance sweep is the adamantane-derived transfer diagnostic: it is not yet frozen as a universal rule, but it quantifies how much of the extra nonbonded tail lives in low-clearance faces.
- The new visible-face clearance distributions support the same point from the complementary angle: surplus realized faces are systematically left-shifted relative to QTAIM-supported faces, especially in the nonbonded regime.

## Outputs

- `edge_level.csv`
- `mask_summary.csv`
- `clearance_sweep.csv`
- `clearance_distribution_summary.csv`
- `molecule_level.csv`
- `summary.json`
