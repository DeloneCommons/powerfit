# J3 candidate-graph recovery

- Manifest: `data/qtaim_main/systems_final.csv`
- Pair-law lookup: `data/proatomic/pairlaw/separator_lookup.csv`
- Manifest rows: **100**
- Processed molecules: **100**
- Skipped rows: **0**
- Candidate cutoffs (Å): **4.0, 4.5, 5.0**

## Overall summary by cutoff

### 4.0 Å

- Candidate inflation factor: **6.837**
- Candidate coverage: **100.00%**
- Recovered support precision / recall / F1 (raw): **0.204 / 1.000 / 0.339**
- Conditional recall (raw): **1.000**
- Recovered support precision / recall / F1 (visible): **0.697 / 0.999 / 0.821**
- Matched true-edge separator RMSE (raw / visible): **0.074642 / 0.074622 Å**
- Extra-edge rate (raw / visible): **0.796 / 0.303**

### 4.5 Å

- Candidate inflation factor: **8.300**
- Candidate coverage: **100.00%**
- Recovered support precision / recall / F1 (raw): **0.204 / 1.000 / 0.339**
- Conditional recall (raw): **1.000**
- Recovered support precision / recall / F1 (visible): **0.697 / 0.999 / 0.821**
- Matched true-edge separator RMSE (raw / visible): **0.076967 / 0.076949 Å**
- Extra-edge rate (raw / visible): **0.796 / 0.303**

### 5.0 Å

- Candidate inflation factor: **9.825**
- Candidate coverage: **100.00%**
- Recovered support precision / recall / F1 (raw): **0.204 / 1.000 / 0.339**
- Conditional recall (raw): **1.000**
- Recovered support precision / recall / F1 (visible): **0.697 / 0.999 / 0.821**
- Matched true-edge separator RMSE (raw / visible): **0.078618 / 0.078599 Å**
- Extra-edge rate (raw / visible): **0.796 / 0.303**

## Bonded vs nonbonded at the reference cutoff

- Bonded: recall(raw) **1.000**, RMSE(raw) **0.079906 Å**.
- Nonbonded: recall(raw) **1.000**, RMSE(raw) **0.058312 Å**.
- Interpretation: separator quality on recovered bonded edges is the main practical signal; nonbonded tails remain a harder regime where graph exactness is less meaningful and representability limitations matter more.

## Full-benchmark takeaway

- On the full frozen benchmark, even the smallest tested cutoff (**4.0 Å**) already covers all observed QTAIM-supported pairs.
- The practical effect of enlarging the cutoff is therefore mainly to inflate the candidate graph, not to improve recall.
- The most informative graph-quality metric on this subset is the visible recovered support, not the raw realized support.

## Outputs

- `molecule_level.csv`
- `subset_summary.csv`
- `qtaim_edge_level.csv`
- `candidate_edge_level.csv`
- `selected_edge_level.csv`
- `summary.json`
