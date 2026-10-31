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

1. Run the focused unit tests and repository consistency audit.
2. Check the seven canonical vector figures by generating temporary comparison
   outputs from their figure scripts.
3. Run the tiny A and B smoke subsets and the J1 audit on committed showcase
   data. Every smoke output is directed to `.smoke/`.
4. Build and validate `manuscript/manuscript.pdf` from its committed sources.
5. Create `build/powerfit-arxiv.zip` with the nested source layout, fresh
   bibliography, pinned official class/style, and their upstream source/license
   support, then extract and compile it in an isolated temporary directory.
6. Record font and embedded-image inventories, reject unresolved archive
   references and Type 3 fonts, and verify that protected files and manuscript
   sources stayed unchanged.

The workflow runs no complete scientific experiment or molecular-generation
pipeline. Historical asset builders are outside the canonical build path.

The font check requires embedding for all fonts except the approved PDF Base14
`Times-Roman` heading in the workflow figure. That standard-font exception is
retained in the compiled article; Type 3 fonts are rejected throughout.

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

For an explicitly requested full scientific rerun, the local audit accepts
`python scripts/check_repo_consistency.py --skip-frozen`. That option leaves the
baseline manifest untouched and keeps the other checks, including pinned-binary
verification. CI always performs the full frozen check.

## Review artifacts

CI uploads the canonical PDF, the arXiv source ZIP, build logs, font/image
inventories, test and integrity reports, and smoke outputs as a workflow
artifact retained for 14 days. It does not publish or submit the manuscript.
Generated outputs live under `build/`, `.smoke/`, or the ignored manuscript build
paths. The final PDFs are checked for successful compilation and font quality;
their binary bytes are not used as a scientific reproducibility criterion.
