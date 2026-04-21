# Experiment J4d: box-margin robustness summary

This report compares precomputed J4b mask-transfer runs produced at different padded-box margins.
Like J4b itself, the reported F1 and ranking scores are computed within each model's realized-face archive; fixed-denominator support recovery against the common QTAIM graph is reported separately in J3.
The table is intended to answer a narrow question: do the visible-graph and clearance diagnostics change materially as the clipping box is enlarged?

## 3A
- voronoi: visible F1 (all/nonbonded) = **0.796 / 0.203**; clearance@0.50 F1 (all/nonbonded) = **0.951 / 0.524**; visible-nonbonded clearance AP = **0.707**; short-distance AP = **0.641**; margin-safe fraction = **1.000**.
- recovered_powerfit: visible F1 (all/nonbonded) = **0.821 / 0.238**; clearance@0.50 F1 (all/nonbonded) = **0.979 / 0.742**; visible-nonbonded clearance AP = **0.830**; short-distance AP = **0.636**; margin-safe fraction = **1.000**.

## 5A
- voronoi: visible F1 (all/nonbonded) = **0.796 / 0.203**; clearance@0.50 F1 (all/nonbonded) = **0.951 / 0.524**; visible-nonbonded clearance AP = **0.707**; short-distance AP = **0.641**; margin-safe fraction = **1.000**.
- recovered_powerfit: visible F1 (all/nonbonded) = **0.821 / 0.238**; clearance@0.50 F1 (all/nonbonded) = **0.979 / 0.742**; visible-nonbonded clearance AP = **0.830**; short-distance AP = **0.636**; margin-safe fraction = **1.000**.

## 7A
- voronoi: visible F1 (all/nonbonded) = **0.796 / 0.203**; clearance@0.50 F1 (all/nonbonded) = **0.951 / 0.524**; visible-nonbonded clearance AP = **0.707**; short-distance AP = **0.641**; margin-safe fraction = **1.000**.
- recovered_powerfit: visible F1 (all/nonbonded) = **0.821 / 0.238**; clearance@0.50 F1 (all/nonbonded) = **0.979 / 0.742**; visible-nonbonded clearance AP = **0.830**; short-distance AP = **0.636**; margin-safe fraction = **1.000**.

## 10A
- voronoi: visible F1 (all/nonbonded) = **0.796 / 0.203**; clearance@0.50 F1 (all/nonbonded) = **0.951 / 0.524**; visible-nonbonded clearance AP = **0.707**; short-distance AP = **0.641**; margin-safe fraction = **1.000**.
- recovered_powerfit: visible F1 (all/nonbonded) = **0.821 / 0.238**; clearance@0.50 F1 (all/nonbonded) = **0.979 / 0.742**; visible-nonbonded clearance AP = **0.830**; short-distance AP = **0.636**; margin-safe fraction = **1.000**.
