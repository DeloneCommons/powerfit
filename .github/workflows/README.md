# GitHub Actions workflows

This directory contains a lightweight repository-integrity and reproducibility
smoke test.

- `repro-smoke.yml` installs Python 3.13 with pip caching, installs the pinned
  `pyvoro2` wheel, runs `pip check`, regenerates manuscript-facing tables and
  figures from the archived sources, verifies that tracked tables and
  manuscript-facing PNG figures stay in sync, runs the dedicated figure binary
  constancy check, runs the repository consistency audit, executes tiny smoke
  subsets for the A and B runners, runs a lightweight J1/QTAIM smoke audit on
  the committed showcase dataset, recreates the flat submission bundle, builds
  the manuscript and flat verification PDFs, and checks that the generated PDFs
  do not contain Type 3 fonts.
- The workflow intentionally does not rerun the heavy molecular generation
  pipeline.
- The figure constancy check exercises representative PDF/PNG figure generation
  in a locked CI environment. The final LaTeX-built manuscript PDFs are checked
  for successful compilation and font hygiene, not byte-for-byte reproducibility.
