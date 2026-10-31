# Preparing and publishing a release

This procedure separates reviewable source changes from an actual project
release and article submission. Preparing a branch, building a PDF, or creating
an arXiv source ZIP does not publish a release or submit the article.

## Identifier and license policy

| Identifier | Meaning | Release policy |
|---|---|---|
| [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557) | `powerfit` concept DOI for all versions. | Keep this project identity; it follows the latest published version. |
| [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558) | Frozen `powerfit` v1.0.0 evidence. | Preserve this exact citation for the experiments and leave its archive unchanged. |
| [10.5281/zenodo.19143984](https://doi.org/10.5281/zenodo.19143984) | `pyvoro2` 0.6.3 computation baseline. | Keep this version-specific software citation for the reported calculations. |
| Future article identifier | The eventual arXiv record and any later journal publication. | Add only after assignment and verification; it identifies the article separately from the project. |

Until another Zenodo version is actually published, the concept DOI continues
to resolve to v1.0.0. It must not be presented as the version DOI of the revised
manuscript or inserted into a new deposit's version-DOI field.

[CITATION.cff](../CITATION.cff) currently cites the evolving project by its
concept DOI and lists the frozen evidence and software references. It omits a
release version and date while those decisions are pending. Likewise,
[.zenodo.json](../.zenodo.json) prepares descriptive metadata without inventing
a new version or DOI. The author affiliation is `Independent researcher`.

The root [LICENSE](../LICENSE) covers first-party materials. Bundled software
retains the terms listed in
[THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md). Keep the Zenodo archive's
mixed-license `Other (Open)` designation; a new release does not relicense
third-party binaries under MIT.

## 1. Complete review before merging

Keep the revision open for author review and the outstanding external review
response. Inspect the complete manuscript and PDF, all scientific qualifications,
figures, bibliography, build changes, and public metadata before merging.

Verify that the scientific evidence remains the frozen v1.0.0 evidence. Changes
to manuscript organization, exposition, figures, and build helpers must not
silently overwrite experimental protocols, numerical outputs, molecular inputs,
the archived environment, or bundled software. Historical documentation in
those trees remains an archive record; the top-level guides provide the current
manuscript crosswalk.

## 2. Validate the exact source to be released

From a clean checkout of the proposed release source, run:

```bash
python scripts/check_repo_consistency.py
python scripts/check_manuscript_figures.py
python -m unittest discover -s tests -v
bash scripts/build_manuscript_pdfs.sh
python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip
```

Use the included, unmodified official `elsarticle` 3.5 class and `elsarticle-num`
bibliography style. Verify their pinned provenance and retain their upstream
source and license material under `manuscript/tex-support/`. The required TeX
packages, including the Debian/Ubuntu `texlive-publishers`
package, are listed in
[manuscript/README.md](../manuscript/README.md#compile-the-article).

Inspect the final PDF for page layout, legible vector figures, unresolved
references or citations, and font problems. Check that it contains the abstract,
Sections 1–9, Appendices A–E, seven figures, four inline tables, and the complete
bibliography. Reject Type 3 fonts and require embedding for all fonts except
the approved PDF Base14 `Times-Roman` heading in the workflow figure. Confirm
that the ZIP preserves nested source paths and includes the freshly built
`manuscript.bbl`, the pinned official class/style, and the allowlisted upstream
source/license support files. Extract the ZIP into a clean temporary directory
and verify it compiles there with the bundled pair and remaining TeX dependencies.
Retain the unmodified `tex-support/glyphtounicode-cmr.tex` mapping file and
check that mathematical symbols remain correct when text is extracted from
the PDF, as well as when the pages are rendered.

Do not run the full scientific rerun as a manuscript-release build step. It
writes new results and belongs in a disposable checkout when separately
evaluating computational reproduction. Do not replace the archived environment
snapshot with the machine used only to render the revised manuscript.

## 3. Decide the release contents and metadata

Before tagging, make these concrete decisions:

- Choose the new release version and release date; neither is assigned by this
  revision. Update release metadata consistently once those values are known.
- Decide whether the Zenodo snapshot will contain source only or both the
  complete revised source and a built article PDF. If a PDF is promised, put it
  into the material actually included in the deposit. A GitHub Release
  attachment must not be assumed to appear in the Zenodo GitHub snapshot.
- Inspect the exact source snapshot and any intended PDF for completeness.
  The ignored local PDF and source ZIP are not automatically tracked release
  contents.
- Check that `.zenodo.json`, `CITATION.cff`, the README, and the manuscript's
  availability statement describe the material that will actually be public.
- Keep the project concept DOI separate from the frozen v1.0.0 citation and
  from any new version DOI. Do not put an unassigned DOI into its own PDF.

## 4. Publish only after the release decision

After review and the explicit release decision, publish a new GitHub Release
through the project's Zenodo integration. Preserve v1.0.0 as the immutable
evidence record. Verify the resulting deposit itself:

- A new version DOI was assigned to the new snapshot.
- The concept DOI remains `10.5281/zenodo.19673557` and now links to the intended
  latest published version.
- The deposited files contain the complete revised manuscript source, its seven
  figure PDFs, and any PDF promised in the release description.
- The creator, affiliation, version, date, related software reference, and
  mixed-license metadata are correct.

Only after these checks should documentation describe the revised manuscript
as available through the latest published project record. Record the actual new
version DOI where a version-specific citation is needed; retain the concept DOI
as the evolving project's citation. Publication of a GitHub branch or merge
alone does not satisfy these checks.

## 5. Connect the eventual article

Submit the reviewed source bundle only when article submission is authorized.
After the arXiv record is assigned and publicly available, add its actual
identifier to the project documentation and Zenodo related-identifier metadata,
using a relation that accurately describes the connection. Do the same for an
eventual journal publication when its identifier exists. Keep article
identifiers distinct from the reproducibility project's concept and version
DOIs.
