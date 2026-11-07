# GitHub Actions workflows

`repro-smoke.yml` validates the canonical manuscript and the original scientific
artifact on pushes, pull requests, and manual dispatch. It installs Python 3.13,
the paper requirements constrained by the unchanged archived lock file, and the
bundled `pyvoro2 0.6.3` wheel, then runs `pip check`. The dependency command is:

```bash
python -m pip install -r environments/requirements-py313.txt -c environments/requirements-lock-py313.txt
```

Its TeX environment includes `latexmk`, BibTeX, the publisher packages, scalable
fonts, and Poppler PDF inspection tools. The pinned, unmodified official
`elsarticle` 3.5 class and `elsarticle-num` style under `manuscript/` take
precedence over the distribution's publisher files. Their source and license
provenance are recorded in
[manuscript/tex-support/README.md](../../manuscript/tex-support/README.md).

## Verification sequence

1. Run the focused unit tests and repository consistency audit, including all
   989 protected scientific files.
2. Check the complete frozen result populations and recompute the four inline
   tables from CSVs; check the seven vector figures using temporary builds.
3. Run the tiny A and B smoke subsets and the J1 audit on committed showcase
   data. Every smoke output is directed to `.smoke/`.
4. Call the arXiv packager once: it builds and validates
   `manuscript/manuscript.pdf`, then creates `build/powerfit-arxiv.zip` with the
   nested source layout, fresh bibliography, pinned official class/style and
   upstream source/license support.
5. Extract and compile that ZIP in an isolated temporary directory, verifying
   that the packaged source dependencies are sufficient.
6. Record font and embedded-image inventories, reject unresolved archive
   references and Type 3 fonts, and verify that protected files and manuscript
   sources stayed unchanged.

The workflow runs no complete scientific experiment or molecular-generation
pipeline. Its result/table checks read frozen evidence. The full A–H/J rerun is
a separate command for a disposable checkout, described in
[scripts/README.md](../../scripts/README.md).

Every figure and article font must be embedded. Type 3 fonts are rejected;
there are no workflow-heading or standard-font exceptions.

## Frozen artifact verification

[`scripts/frozen_artifacts.sha256.json`](../../scripts/frozen_artifacts.sha256.json)
records SHA256 digests of the original Git-tracked files at public commit
`80933a14c57d4766bd2c03b2990d949a452031fc`. It covers `experiments/`, `results/`,
`data/`, `environments/`, `external_software/`, `scripts/qtaim/`, and the shared
scientific figure helper `scripts/_figure_io.py`.

The repository audit verifies this record before and after CI. It rejects
changed or missing baseline files and unexpected files in protected directories,
while allowing Python/tool caches. Verification reads the committed manifest and
works without Git history, including in a downloaded repository source archive.
No build or check refreshes the manifest. The existing pinned-binary digest,
runtime-requirement, source-link, and absolute-path checks also remain active.

The integrity check has no bypass mode. A disposable checkout containing new
scientific results is checked with `check_rerun_results.py` and
`check_manuscript_tables.py`, rather than being relabeled as the frozen archive.

## Review artifacts

CI uploads the canonical PDF, the arXiv source ZIP, build logs, font/image
inventories, test and integrity reports, and smoke outputs as a workflow
artifact retained for 14 days. It does not publish or submit the manuscript.
Generated outputs live under `build/`, `.smoke/`, or the ignored manuscript build
paths. The final PDFs are checked for successful compilation and font quality;
their binary bytes are not used as a scientific reproducibility criterion.
