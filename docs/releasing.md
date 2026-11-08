# Releasing powerfit v2.0.0

The revised article and reproducibility sources form v2.0.0; the underlying
scientific evidence remains the unchanged [v1.0.0 archive](https://doi.org/10.5281/zenodo.19673558).
This is a **manual Zenodo release**, not a GitHub-to-Zenodo integration.
No arXiv submission or scientific rerun is part of this procedure.

## Identifiers and licenses

| Identifier | Role |
|---|---|
| [10.5281/zenodo.24047266](https://doi.org/10.5281/zenodo.24047266) | **Reserved version DOI** for the v2.0.0 Zenodo draft; resolves after publication. |
| [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557) | **Concept DOI** for all versions of powerfit. |
| [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558) | Frozen v1.0.0 scientific evidence. |
| [10.5281/zenodo.19143984](https://doi.org/10.5281/zenodo.19143984) | pyvoro2 0.6.3 software used for the calculations. |

The v2.0.0 DOI was reserved via **New version** on the existing Zenodo record.
Keep that draft and its reserved DOI; do not open an unrelated new record.
[CITATION.cff](../CITATION.cff) uses the version DOI for citations and lists
the concept DOI separately. Do not add a release date before publication.

The [MIT license](../LICENSE) covers first-party repository materials.
Bundled software and official LaTeX support retain their
[own licenses](../THIRD_PARTY_LICENSES.md). Keep **Other (Open)** in Zenodo
for the mixed-license archive, with the explanation from
[.zenodo.json](../.zenodo.json). The latter is a reference for manual entry:
uploading a ZIP does not import its metadata automatically.

## Release steps

1. Review and merge the release-preparation PR after GitHub Actions passes.
   Confirm the frozen-file, PDF, figure, table, and extracted arXiv source checks.
   The full scientific rerun is unnecessary for this manuscript-only revision.
2. Create and push the tag `v2.0.0` at that reviewed commit. A GitHub Release
   page is optional; the immutable Git tag identifies the exact source version.
3. In a clean checkout of the tag, rebuild the reviewed article PDF:

   ```bash
   git checkout v2.0.0
   bash scripts/build_manuscript_pdfs.sh
   python scripts/check_repo_consistency.py
   ```

4. Download the **v2.0.0 tagged source ZIP** from GitHub, or make the equivalent
   archive locally (from the same checkout):

   ```bash
   mkdir -p build
   git archive --format=zip --prefix=powerfit-v2.0.0/ \
     --output=build/powerfit-v2.0.0-source.zip v2.0.0
   ```

   Extract that ZIP into a temporary directory. Copy the freshly built
   `manuscript/manuscript.pdf` into the extracted
   `powerfit-v2.0.0/manuscript/` directory, beside `manuscript.tex`.
   Re-zip the **single top-level `powerfit-v2.0.0/` directory**, naming the
   result `powerfit-v2.0.0.zip`.

5. Inspect the final ZIP: exactly one top-level source directory, a working
   `manuscript/manuscript.pdf`, seven committed figure PDFs, the original
   `experiments/`, `results/`, `data/`, `external_software/`, and the
   license notices. The PDF is the only intentionally added build output.
6. In the **existing v2.0.0 Zenodo draft**, upload `powerfit-v2.0.0.zip`.
   Confirm its version DOI `10.5281/zenodo.24047266`, concept DOI
   `10.5281/zenodo.19673557`, resource type **Software**, version **2.0.0**,
   creator/ORCID, affiliation **Independent researcher**, license **Other
   (Open)**, and related pyvoro2 reference. Then publish when authorized.
7. After publication, verify that the reserved version DOI now resolves to
   the correct record and that the concept DOI follows the latest version.

Do not attach an arXiv identifier until arXiv has actually assigned it.
If a GitHub Release page is later useful for discoverability, reuse the
`v2.0.0` tag and link to the new Zenodo version. First ensure automatic
GitHub-to-Zenodo ingestion is **off** to avoid creating a duplicate record.
