# Third-party licenses and notices

This repository contains first-party material created for the powerfit
reproducibility artifact together with bundled third-party runtime artifacts
under `external_software/` and official LaTeX support files under
`manuscript/`.

## Scope of the root license

The root [LICENSE](LICENSE) file applies to the first-party repository content,
including the manuscript sources, analysis scripts, result summaries, and other
original project materials in this repository unless stated otherwise in a more
specific file-level notice.

## Bundled third-party artifacts

The following bundled artifacts are distributed under their own upstream terms
and notices. Their presence in this repository does not relicense them under the
root MIT license. The Zenodo record for the archive as a whole is therefore
marked as Other (Open), while this file records the concrete license split.

### pyvoro2 wheel

- Artifact: `external_software/pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl`
- Upstream license: LGPL-3.0-or-later
- Provenance manifest: `external_software/pyvoro2-version.txt`

### Multiwfn noGUI executable

- Artifact: `external_software/Multiwfn_noGUI`
- Upstream notice and usage conditions: `external_software/Multiwfn_LICENSE.txt`
- Provenance manifest: `external_software/multiwfn-version.txt`
- Citation note: `external_software/How_to_cite_Multiwfn.pdf`

### Official elsarticle publication support

- Bundled class: [manuscript/elsarticle.cls](manuscript/elsarticle.cls), official
  `elsarticle` 3.5 (2026-01-09).
- Bundled numerical bibliography style:
  [manuscript/elsarticle-num.bst](manuscript/elsarticle-num.bst), version 2.1 from
  the same official upstream package.
- Upstream license: LaTeX Project Public License 1.3 or later, as stated in the
  retained upstream file headers and documentation. These files are not covered
  by the repository's MIT license.
- Provenance, checksums, and source/license documentation:
  [manuscript/tex-support/README.md](manuscript/tex-support/README.md).
- Retained upstream support: `manuscript/tex-support/README.upstream`,
  `elsarticle.dtx`, and `elsarticle.ins`.

The class and bibliography style are distributed unchanged, including their
upstream headers. They are pinned to make the canonical article and arXiv source
archive use the same official publisher version across TeX installations. The
arXiv bundle carries the class/style and the listed source/license support
files. Preserve those notices and consult the upstream terms when
redistributing or modifying them.

### Computer Modern Unicode mappings

- File: [manuscript/tex-support/glyphtounicode-cmr.tex](manuscript/tex-support/glyphtounicode-cmr.tex),
  copied unchanged from the TeX Live `pdfx` package.
- Upstream license: LaTeX Project Public License 1.2 or later.
- Copyright: 2008 Han The Thanh, 2014 Peter Selinger, and 2018 Ross Moore,
  as recorded in the retained file header.
- Provenance and checksum:
  [manuscript/tex-support/README.md](manuscript/tex-support/README.md#computer-modern-unicode-mappings).

The article loads this mapping data directly to preserve mathematical text
extraction across TeX versions; it does not load the `pdfx` package itself.
The file is included in the arXiv source bundle and retains its upstream
license independently of the repository's MIT license.

## User responsibility

Users who reuse, redistribute, or repackage this repository should review the
upstream terms for each bundled third-party artifact and comply with the
corresponding license and citation requirements.
