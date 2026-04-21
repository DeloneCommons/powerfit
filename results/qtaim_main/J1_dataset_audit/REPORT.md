# J1 dataset audit

Processed manifest: `data/qtaim_main/systems_final.csv`

Current processing status:
- manifest rows: **100**
- processed molecules: **100**
- skipped rows: **0**

Topology summary on the full frozen benchmark:
- total QTAIM BCP edges: **3975**
- molecules with at least one RCP: **90.0%** (90/100)
- molecules with at least one CCP: **9.0%** (9/100)
- molecules with at least one nonbonded BCP: **84.0%** (84/100)
- nonbonded BCP fraction over all BCP edges: **6.84%**

Connector-projection audit:
- median off-axis distance: **0.00465 Å**
- 95th percentile off-axis distance: **0.09687 Å**
- maximum off-axis distance: **0.39996 Å**
- edges with off-axis distance ≤ 0.02 Å: **91.57%**

Bonded vs nonbonded connector-projection split:
- bonded edges: **3703** total, median off-axis **0.00448 Å**, low-offset share **98.22%**
- nonbonded edges: **272** total, median off-axis **0.15077 Å**, low-offset share **1.10%**

Interpretation notes:
- The full frozen benchmark is not topologically trivial: higher-order critical points are already common.
- The explicit-H molecular-graph audit shows that many molecules contain QTAIM-supported nonbonded contacts.
- The pooled off-axis summary is dominated by bonded edges. Bonded BCPs are strongly connector-aligned, whereas the nonbonded subset is a much harsher proxy-mismatch regime and should be read accordingly in the main text.
- In the current subset, **4** BCP edges fall into graph-distance class 2–3; all remaining nonbonded BCP edges occur at graph distance ≥ 4. This supports the use of a simple bonded-vs-nonbonded split in the main text, while keeping the exact graph distance in the edge-level export for optional supplement analysis.

Files:
- `molecule_level.csv`: one row per processed molecule
- `edge_level.csv`: one row per QTAIM BCP-supported pair
- `pair_type_summary.csv`: element-pair composition summary
- `graph_distance_summary.csv`: bonded vs nonbonded summary, plus exact graph distance bins
- `skipped_rows.csv`: rows skipped because inputs were incomplete or inconsistent
