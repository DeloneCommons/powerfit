# Pinned official TeX support

The article uses the unmodified official **elsarticle 3.5 (2026-01-09)**
class and its numeric bibliography style. These files preserve the verified
layout across systems whose TeX distribution still ships an older class.
They do not imply a journal submission destination.

The upstream package is [elsarticle on CTAN](https://ctan.org/pkg/elsarticle).
The distribution was obtained from the
[CTAN mirror](https://mirrors.ibiblio.org/pub/mirrors/CTAN/macros/latex/contrib/elsarticle.zip).
Its SHA-256 is
`f25a3e1b006e0f86abb091a02f3afa7c6d60491665c7aa89f70cc5609e14d9dc`.

| File | SHA-256 |
|---|---|
| `../elsarticle.cls` | `40af0200a8ad6777126f93bf7be6ab3046fa7c3ef1073307f0809703602e59da` |
| `../elsarticle-num.bst` | `f04dfa2f78d0198ab8e4055b609dc0b91bdb730743cbbd549d84270f20d11394` |
| `elsarticle.dtx` | `5679fe34806e0a08d3747f96e472126f520b6ccd3e92118c14bdd26e9e101e2e` |
| `elsarticle.ins` | `fb7a1005446d3217a77dc4496a10837d01f5ea3a177859054bf0daac0d4072c1` |
| `README.upstream` | `c6eb2fcd2741bf2836ca40c8e8d7f5ff2cc49e52d92b0d96051385299e021233` |

The class is generated from these upstream sources by running
`latex elsarticle.ins` in a temporary directory containing the `.ins` and
`.dtx` files. The resulting class is byte-identical to the pinned copy.
The `.bst` is copied unchanged from the upstream distribution. The source
archive includes this directory along with the class and bibliography style.

Copyright 2007–2026 Elsevier Ltd. These upstream files retain their original
notices and are distributed under the
[LaTeX Project Public License 1.3 or later](https://www.latex-project.org/lppl/).
They are not covered by this repository's MIT license. The complete upstream
distribution, documentation, and other bibliography styles are available from
CTAN; only the files supporting this article are included here.

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
