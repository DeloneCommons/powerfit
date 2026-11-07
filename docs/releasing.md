# Preparing and publishing v2.0.0

The revised article and software/reproducibility sources are released together, but
**the experiments remain the frozen v1.0.0 evidence**. Preparing a ZIP is not an
arXiv submission, GitHub Release, or Zenodo publication. The v2.0.0 release uses
**manual Zenodo versioning**, not GitHub-to-Zenodo automatic ingestion.

## Persistent identifiers and licenses

| Identifier | Purpose |
|---|---|
| [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557) | All-versions concept DOI of the evolving powerfit project. |
| [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558) | Immutable version DOI of the v1.0.0 scientific evidence used in the article. |
| [10.5281/zenodo.19143984](https://doi.org/10.5281/zenodo.19143984) | Version-specific pyvoro2 0.6.3 software DOI for the reported calculations. |
| New version DOI | Assigned by Zenodo only when the v2.0.0 version is created/published. Do not invent it or substitute the concept DOI. |
| Article identifier | An arXiv ID or journal DOI may be linked after it exists, not beforehand. |

The root [MIT license](../LICENSE) covers first-party content, including the
manuscript source. Bundled pyvoro2, Multiwfn, and LaTeX support materials retain
their [upstream terms](../THIRD_PARTY_LICENSES.md). For the mixed-license ZIP,
retain the Zenodo record's **Other (Open)** designation and its explanation.
The metadata in [.zenodo.json](../.zenodo.json) and
[CITATION.cff](../CITATION.cff) is a reference for the *manual* form; Zenodo
does not automatically import these files from a manually uploaded ZIP.
The release date and new version DOI are unknown until publication and must not
be prefilled with guesses.

## 1. Check the intended source

Before tagging, merge the release-preparation changes to `main`, review the
exact commit, and verify the CI run for that commit passed. In a clean checkout,
run the regular checks if needed:

```bash
python scripts/check_repo_consistency.py
python scripts/check_rerun_results.py
python scripts/check_manuscript_tables.py
python scripts/check_manuscript_figures.py
python -m unittest discover -s tests -v
python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip
```

This checks the 989 protected files, the four printed tables, the seven figures,
the PDF build and the separately compilable arXiv source archive. Examine the
65-page PDF, its front matter, figures, references, and Appendices A--E.
The official bundled `elsarticle` 3.5 class and BibTeX style, their upstream
license source, and the Unicode mapping are part of the manuscript sources.
Do not rerun the full experiments or upstream quantum chemistry as a release
build step: these would write new result files. For experimental reproduction,
use a disposable checkout as described in [scripts/README.md](../scripts/README.md).

## 2. Create an immutable source tag and one Zenodo ZIP

After author approval and successful checks, create a `v2.0.0` tag pointing to
the reviewed `main` commit and push it to GitHub. The tag alone is sufficient
to identify the exact release source; a GitHub Release page is optional.

From a **clean checkout at that exact tagged commit**, run:

```bash
python scripts/build_zenodo_archive.py --tag v2.0.0 --output build/powerfit-v2.0.0.zip
```

This command rebuilds and verifies the canonical manuscript PDF, checks frozen
repository integrity, exports the tracked tree using `git archive v2.0.0`, and
adds **only** the compiled PDF at `manuscript/manuscript.pdf`. It refuses a
mismatched HEAD or modified tracked files and checks the completed ZIP.
Its output is a **single file** named `powerfit-v2.0.0.zip` with this layout:

```text
powerfit-v2.0.0/
  README.md
  CITATION.cff
  .zenodo.json
  manuscript/
    manuscript.tex
    manuscript.pdf
    sections/
    appendices/
    figures/
  experiments/
  results/
  data/
  ... all other tracked release files ...
```

The Git tree excludes ignored build outputs. The only intentionally included
untracked build product is the finished PDF. The ZIP includes the frozen
scientific data and bundled third-party artifacts with their license notices.
Retain the printed tag commit SHA and ZIP SHA256 in the release notes.
Do not substitute a ZIP from moving `main`, repackage it by hand, or assume
that a GitHub-generated source ZIP contains the ignored PDF.

## 3. Publish a *new version* on Zenodo manually

Open the **existing v1.0.0 record** at
[10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558) while
signed in as an owner and select **New version**. Do *not* create an unrelated
new upload. For the v2.0.0 version:

1. Upload the single `powerfit-v2.0.0.zip` from the exact tag; there is no need
   to import the old v1.0.0 files, because the ZIP includes the frozen evidence.
2. Keep resource type **Software**; use the v2.0.0 version number, actual
   publication date, creator/ORCID and Independent researcher affiliation.
   Include the scope and frozen-baseline explanation from `.zenodo.json`.
3. Keep the mixed-license **Other (Open)** value and upstream license notices;
   link to the separately published pyvoro2 0.6.3 record.
4. Check that this draft is in the *existing version family* and that its
   all-versions concept DOI remains `10.5281/zenodo.19673557`. Do not type
   that concept DOI into the new record's **version DOI** field.
5. Check the archive checksum and ZIP layout; then publish the new version.
   Record the newly assigned **version DOI** and verify both version and
   concept DOI links afterward.

A single ZIP also follows Zenodo's manual software-upload guidance for optional
Software Heritage archival. It trades a directly previewable PDF on the Zenodo
record page for a single self-contained, source-plus-PDF release file.

## 4. Optional GitHub Release page, and later article publication

A GitHub Release is **not necessary** for versioning once `v2.0.0` is tagged
and deposited on Zenodo. It can be useful for discoverable release notes and a
link to the new Zenodo version DOI. If created, use the existing `v2.0.0` tag,
explain the frozen v1.0.0 evidence, and link to the manual Zenodo record.
**Verify the repository is not enabled for automatic Zenodo GitHub ingestion**
before publishing a GitHub Release; otherwise an unwanted second deposit may
be created. GitHub's auto-generated source ZIP does not contain the PDF.

After the arXiv manuscript receives its identifier, link to it in the project
README and Zenodo related identifiers using the correct relation. A future
journal DOI is similarly separate from the project concept and version DOIs.
No arXiv submission or scientific rerun is part of this release procedure.
