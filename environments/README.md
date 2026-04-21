# Python environments

This directory records both the **minimal runtime environment** needed to rerun
the archived paper artifact and the **reference environment** actually used for
this frozen snapshot.

Files:

- `requirements-py313.txt` — minimal paper-side Python dependencies around the
  pinned `pyvoro2` wheel, including the committed-data Experiment J analyses.
- `requirements-dev.txt` — optional developer conveniences layered on top of the
  minimal runtime environment (`pytest`, `ruff`). They are not required merely
  to rerun the archived experiments or rebuild the manuscript assets.
- `requirements-lock-py313.txt` — exact Python distribution snapshot captured
  from the final release environment with
  `scripts/capture_environment_snapshot.py`.
- `system.txt` — reference system description for the archived snapshot.

## Runtime assumptions

The bundled wheel in `../external_software/` is a Linux manylinux artifact, so
this repository assumes Linux (including WSL2) for the fully bundled binary
path. The repository logic itself is not Linux-specific: on other platforms,
install `pyvoro2==0.6.3` from PyPI or build the same version from source, then
install the requirements from `requirements-py313.txt`.

## Minimal paper-side environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r environments/requirements-py313.txt
pip install external_software/pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl
```


## Capturing the exact release-time snapshot

When you are ready to freeze the final public artifact, run the dedicated helper
from the clean paper-side environment you want to archive:

```bash
python scripts/capture_environment_snapshot.py
```

That helper rewrites `system.txt` and `requirements-lock-py313.txt`. It is
intentionally **not** part of the normal rerun/build path, because the exact
snapshot should be updated only at release time. This locked snapshot also
defines the determinism boundary for the manuscript-facing Python figure
generators: same repo plus this locked environment should reproduce identical
figure bytes.

## Why keep both minimal requirements and an exact lock file?

The repository is frozen around a paper artifact, so most users only need the
minimal runtime environment. The separate `requirements-dev.txt` keeps lint/test
extras out of the archival runtime path while still documenting the tools used
for optional local checks.

## Package roles

The minimal runtime requirements have intentionally narrow roles:

- `numpy`, `scipy` — numerical kernels and linear algebra used by the benchmarks;
- `pandas` — aggregation of archived runs and LaTeX-table export helpers;
- `matplotlib` — manuscript figure generation;
- `PyYAML` — loading archived YAML protocols;
- `jinja2` — template support used by the table-generation path;
- `rdkit` — committed-data molecular graph helpers used by the Experiment J analyses;
- `tqdm` — console progress bars used by the longer Experiment J analyses.

The development-only extras are equally small:

- `pytest` — optional local test execution;
- `ruff` — optional linting / style checks.


## Optional QTAIM / PySCF helper environment

The frozen paper artifact itself does not require PySCF or Multiwfn, but the
optional QTAIM helper layer does. Use `requirements-qtaim.txt` when you want
to run the geometry-optimization / single-point / topology helper scripts:

```bash
pip install -r environments/requirements-qtaim.txt
```

The current geometry-optimization helper defaults to the `geometric`
optimizer backend, so the `geometric` package is included in that
requirements file.
