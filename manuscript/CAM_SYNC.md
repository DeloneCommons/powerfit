# CAM manuscript synchronization

This is a manuscript and build-infrastructure update on `main`, not a scientific
revision or a new release.

## Pinned provenance

- Public baseline: `DeloneCommons/powerfit`, `main` at
  `4944a06cd508b0f087d7bab260a545458bfc1c4b` (the v2.0.0 source tree).
- Authoritative manuscript: `IvanChernyshov/powerfit-cam`, `main` at
  `4e665d370935fbaf4da25ce862ddaf76890271e9`, the final CAM submission source.
- Import: exactly 27 allowlisted files from that CAM commit, with **no byte
  transformations**: nine `sections/*.tex`, five `appendices/*.tex`, seven
  `figures/*.pdf`, `manuscript.tex`, `refs.bib`, `sn-jnl.cls`,
  `sn-mathphys-ay.bst`, `TEMPLATE_PROVENANCE.md`, and
  `tex-support/glyphtounicode-cmr.tex`.

The CAM source already contains its revised abstract, front matter and
declarations, author–year citation grammar, continuous table/figure numbering,
figure-caption disclosure and bibliography formatting repairs. Those approved
changes are imported as written. Reference identities, mathematical content,
proofs and numerical evidence are preserved; no paper text is independently
rewritten for this synchronization. The publisher-file provenance is retained
in [TEMPLATE_PROVENANCE.md](TEMPLATE_PROVENANCE.md).

## Public build adaptations

The public repository retains its existing layout and commands:
`scripts/build_manuscript_pdfs.sh` and `scripts/make_arxiv_bundle.py`. The source
bundle retains nested includes, original figure filenames, the Unicode mapping
file, a freshly generated bibliography, and publisher/source provenance. It
does not use the journal portal's flattened/renamed export. No private
submission materials or administrative records are imported or packaged.

The dependency collector explicitly requires the class-selected author–year
BST and the provenance notices. Git attributes preserve the upstream publisher
bytes. The five obsolete Elsevier class/style/extraction/documentation files
are removed and their current-tree licensing references replaced. Public build
and licensing documentation is adapted; the imported files remain unchanged.

The unchanged CAM baseline produces underfull-box notices and hyperref's
`Difference (2) between bookmark levels is greater` notice with local TeX Live
2025. For the CAM class only, validation permits these layout notices while
retaining them in the logs. Other warnings, unresolved citations/references,
bibliography warnings, overfull boxes and font-quality failures remain fatal.
See the [build guide](https://github.com/DeloneCommons/powerfit/blob/main/manuscript/README.md).

## Figure-byte identity

All seven figures match both the authoritative CAM commit and the public
baseline byte-for-byte; they were not regenerated during the import.

| Figure PDF | SHA-256 |
|---|---|
| `figure_02_separators.pdf` | `7f62eb8fe019bc8c6017827302eb5545a161d293e7838ef39fbd7100ca39295c` |
| `figure_03_cycle.pdf` | `a26256342ef2296161284e67c553503b85cd97212e8625b2c99dee09ee180876` |
| `figure_04_realization.pdf` | `b4ca9b97cec6f222a4e242c1e9948848e19a9393fcfc9a04facff6c6e461f99e` |
| `figure_05_workflow.pdf` | `7842a137001f6782858c89a209edff5c1ccb012ba50ccabe36fb8f0f2d2541ae` |
| `figure_C_identifiability.pdf` | `012a2fb5a591a734a178a1780515cf46508623fba0fb260d458fc66476303b15` |
| `figure_E_bcp_projection.pdf` | `9db6ac3bad044b4e24bd91822574c95da904f88d9ddcbd93231be02a67db6dee` |
| `figure_G_mismatch.pdf` | `f961fe81f33d8ef77a475e91be7f8b898188ad6b43551f8e9668d024430eec72` |

## Frozen evidence and archive identity

All 989 files protected by `scripts/frozen_artifacts.sha256.json` and the
manifest itself remain unchanged. Experimental code, datasets, results,
scientific dependencies and their pinned manifests are not updated. Figure
verification uses temporary outputs; no full experiment or molecular
wavefunction generation is needed for this synchronization.

The published v1.0.0 and v2.0.0 archives retain their original meanings and
contents. `CITATION.cff`, `.zenodo.json`, and `docs/release-v2.0.0.md` are retained
byte-for-byte as historical archive metadata. In particular, the
[v2.0.0 version DOI](https://doi.org/10.5281/zenodo.24047266) identifies the
published v2.0.0 snapshot, not this CAM-synchronized `main`. The
[concept DOI](https://doi.org/10.5281/zenodo.19673557) covers published project
versions. This update creates no tag, GitHub Release or Zenodo deposit.
