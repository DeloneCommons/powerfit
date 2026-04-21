# J2 true-support separator ladder

- Manifest: `data/qtaim_main/systems_final.csv`
- Pair-law lookup: `data/proatomic/pairlaw/separator_lookup.csv`
- Manifest rows: **100**
- Processed molecules: **100**
- Skipped rows: **0**
- QTAIM BCP-supported edges: **3975**

## Overall separator ladder (Å RMSE)

- Midpoint: **0.133238**
- Frozen proatomic local law: **0.045181**
- Frozen proatomic + one-shot powerfit: **0.047325**
- Support-conditioned power-diagram ceiling: **0.016934**

## Main interpretation

- The frozen proatomic law closes **75.7%** of the midpoint-to-ceiling gap on the full frozen benchmark.
- One-shot reconciliation of proatomic targets changes separator positions only slightly (distortion RMSE **0.011374 Å**), but does **not** improve true-edge separator RMSE on this subset.
- All requested true-support edges are realized after one-shot powerfit for **100/100** processed molecules under the proatomic targets and **100/100** under the QTAIM-target ceiling.

## Heteronuclear subset

- Edges: **2605**
- Midpoint RMSE (Å): **0.164278**
- Proatomic RMSE (Å): **0.054894**
- Proatomic gap closure: **75.8%**

## Low-offset subset

- Offset threshold: **0.02 Å**
- Edges within threshold: **3640**
- Ceiling RMSE (Å): **0.006321**

## Clean connector-aligned heteronuclear subset

- Edges: **2437** across **100** molecules.
- Ceiling RMSE (Å): **0.006018** with realized fraction **100.0%**.
- Interpretation: when supervision is connector-aligned and chemically nontrivial, the fixed-site power-diagram model is not intrinsically too crude.

## Bonded vs nonbonded split

- Bonded edges: **3703**; proatomic RMSE **0.045715 Å**, ceiling **0.006227 Å**.
- Nonbonded edges: **272**; proatomic RMSE **0.037151 Å**, ceiling **0.060519 Å**.
- Interpretation: the bonded subset retains a large power-diagram-improvable gap, while the nonbonded subset already exposes strong model mismatch on the true support. This is exactly why the molecular section should emphasize separator quality on important/bonded edges and treat the nonbonded tail as proxy- and representability-limited rather than as a target for forced exact reconstruction.

## Outputs

- `edge_level.csv`
- `molecule_level.csv`
- `subset_summary.csv`
- `pair_type_summary.csv`
- `summary.json`
