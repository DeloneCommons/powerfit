# Experiments

Frozen experiment code and protocols for the paper artifact live here.

## Read this directory in this order

1. [registry/README.md](registry/README.md) — manuscript labels A--H and J mapped
   to concrete files and result roots.
2. [configs/README.md](configs/README.md) — current YAML protocols.
3. [runners/README.md](runners/README.md) — executable experiment entry points.
4. [analysis/README.md](analysis/README.md) — manuscript-facing summaries,
   figures, and tables.
5. [generators/README.md](generators/README.md) — synthetic instance generation
   and data-preparation helpers.

## Scope

- Experiments **A--H** form the compact synthetic validation suite used by the
  manuscript.
- Experiment **J** is configured by
  `experiments/configs/qtaim_molecular.yaml`, but most of its execution and
  analysis live under `scripts/qtaim/` because that branch includes the
  molecular preprocessing pipeline. The final artifact is easiest to read as J1
  (dataset audit), J2 (true-support ladder), J3 (candidate-graph recovery), and
  J4a--J4d (local validation, mask transfer, representative geometry, and
  box-margin robustness).
- The old Experiment I independent-partition benchmark is historical and is not
  part of the current manuscript build path.

Results live under `../results/` and are committed when they are part of the
frozen paper artifact.
