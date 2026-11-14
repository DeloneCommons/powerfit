# Pinned official TeX support

The article uses the unmodified official Springer Nature `sn-jnl.cls` and
`sn-mathphys-ay.bst` for CAM's author–year format. The official December 2024
distribution, file identifiers and SHA-256 checksums are recorded in the
unchanged [template provenance](../TEMPLATE_PROVENANCE.md). The pinned CAM and
public repository baselines are recorded in [CAM_SYNC.md](../CAM_SYNC.md).

The class header specifies the LaTeX Project Public License 1.3c or later,
including its LaTeX base-system redistribution notice. It credits the LaTeX3
Project and the individual authors listed in the file. The bibliography-style
header specifies LPPL 1.0 or later and additionally says to use the file without
changes. Both complete headers are retained; neither file is covered by this
repository's MIT license. Consult the
[LPPL](https://www.latex-project.org/lppl/) and the official distribution when
redistributing these files.

The public source archive includes the same class/style, template provenance,
synchronization note, and this notice. Standard packages and the LaTeX base
system remain TeX-distribution dependencies. Git attributes preserve the
publisher bytes, including the official class's CR-only line endings.

## Computer Modern Unicode mappings

The unmodified `glyphtounicode-cmr.tex` from the
[pdfx package on CTAN](https://ctan.org/pkg/pdfx) supplies Unicode mappings
for Computer Modern mathematical glyphs. It is loaded directly, without
loading `pdfx`, to preserve correct text extraction on older pdfTeX/TeX Live
installations. It changes PDF text mappings only, without changing the
equations, font programs, glyph placement, or page layout.

The copy was obtained from TeX Live's
`tex/latex/pdfx/glyphtounicode-cmr.tex` (2018-09-18 mapping revision), distributed
in Debian/Ubuntu `texlive-latex-extra` version `2023.20240207-1`.
Its SHA-256 is
`4390c8bfb8a6f709b90b7502ae4accb74815a5269d99f18bb97c1dde95c16c2a`.
The manuscript explicitly enables `\pdfgentounicode=1`, and its dependency
closure includes this file in the arXiv source archive.

Copyright 2008 Han The Thanh, 2014 Peter Selinger, and 2018 Ross Moore.
The complete original header is retained. This upstream file is distributed
under the LaTeX Project Public License 1.2 or later and is not covered by the
repository's MIT license.
