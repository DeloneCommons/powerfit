# Experiment J4a: local theorem-to-code validation

- Source edge-level CSV: `results/qtaim_main/J4_mask_transfer_refresh/edge_level.csv`
- Total faces checked: **38746**
- Total visible faces checked for clearance: **11677**
- Total visibility mismatches: **0**
- Maximum absolute clearance mismatch on visible faces: **3.52496e-15**

## Per-model summary

### voronoi

- Faces checked: **19278**
- Visible faces checked for clearance: **5974**
- Visibility mismatches: **0**
- Visibility agreement fraction: **1.000000**
- Max / mean / median $|\Delta c|$: **3.52496e-15 / 3.27094e-16 / 2.22045e-16**

### recovered_powerfit

- Faces checked: **19468**
- Visible faces checked for clearance: **5703**
- Visibility mismatches: **0**
- Visibility agreement fraction: **1.000000**
- Max / mean / median $|\Delta c|$: **3.10862e-15 / 3.93324e-16 / 2.77556e-16**

## Interpretation

The clipped analytic local-support formulas are numerically identical to the tessellation-derived diagnostics on the released J4 archive up to machine precision on clearance and exactly on the visibility boolean.
