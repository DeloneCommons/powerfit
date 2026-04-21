# Experiment registry

This directory maps the lettered experiment families used in the manuscript to
the concrete files in this repository.

## How to use this directory

Start here when you want a stable manuscript-to-code crosswalk.

- `experiments/generators/` contains synthetic/data-preparation code.
- `experiments/runners/` launches benchmark sweeps.
- `experiments/analysis/` produces manuscript-facing summaries.
- `experiments/configs/` stores the frozen run protocols.
- `results/` stores the archived outputs.

The current manuscript uses Experiments A--H and J. The old `I_*` branch is a
historical secondary benchmark and is not part of this released paper artifact.
