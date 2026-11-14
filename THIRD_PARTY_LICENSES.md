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
- The wheel includes Voro++ as its three-dimensional tessellation backend;
  Voro++ retains its separate upstream redistribution conditions, reproduced below.

### Voro++ (embedded in the pyvoro2 wheel)

This notice accompanies the bundled binary wheel. The full upstream license
text is reproduced from
[`pyvoro2` v0.6.3: `vendor/voro++/LICENSE`](https://github.com/DeloneCommons/pyvoro2/blob/v0.6.3/vendor/voro%2B%2B/LICENSE).
It applies to the incorporated Voro++ code independently of the wheel's
LGPL license and this repository's MIT license.

```text
Voro++ Copyright (c) 2008, The Regents of the University of California, through
Lawrence Berkeley National Laboratory (subject to receipt of any required
approvals from the U.S. Dept. of Energy). All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met: 

(1) Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer. 

(2) Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation
and/or other materials provided with the distribution. 

(3) Neither the name of the University of California, Lawrence Berkeley
National Laboratory, U.S. Dept. of Energy nor the names of its contributors may
be used to endorse or promote products derived from this software without
specific prior written permission. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. 

You are under no obligation whatsoever to provide any bug fixes, patches, or
upgrades to the features, functionality or performance of the source code
("Enhancements") to anyone; however, if you choose to make your Enhancements
available either publicly, or directly to Lawrence Berkeley National
Laboratory, without imposing a separate written license agreement for such
Enhancements, then you hereby grant the following license: a  non-exclusive,
royalty-free perpetual license to install, use, modify, prepare derivative
works, incorporate into other computer software, distribute, and sublicense
such enhancements or derivative works thereof, in binary and source code form.
```

### Multiwfn noGUI executable

- Artifact: `external_software/Multiwfn_noGUI`
- Upstream notice and usage conditions: `external_software/Multiwfn_LICENSE.txt`
- Provenance manifest: `external_software/multiwfn-version.txt`
- Citation note: `external_software/How_to_cite_Multiwfn.pdf`

### Official Springer Nature publication support

- Bundled class: [manuscript/sn-jnl.cls](manuscript/sn-jnl.cls), internal
  identifier `2019/11/18 v0.1`.
- Bundled author–year bibliography style:
  [manuscript/sn-mathphys-ay.bst](manuscript/sn-mathphys-ay.bst),
  `2024/07/19 v1.1`.
- Distribution: official Springer Nature December 2024 template, copied
  byte-for-byte from the pinned CAM manuscript source.
- Class terms: LaTeX Project Public License 1.3c or later, including the
  retained LaTeX base-system redistribution notice in its header.
- Bibliography-style terms: LaTeX Project Public License 1.0 or later; its
  header additionally says to use it without changes.
- Provenance, official distribution link and checksums:
  [manuscript/TEMPLATE_PROVENANCE.md](manuscript/TEMPLATE_PROVENANCE.md).

These files retain their complete upstream headers and are not covered by
the repository's MIT license. The public source bundle includes the same
unchanged class/style and their provenance; standard packages and the LaTeX
base system remain TeX-distribution dependencies. Preserve the notices and
consult the upstream terms when redistributing them. The obsolete Elsevier
class, bibliography style, extraction sources and notices have been removed
from the current tree; this does not change the contents or licensing of the
published archives.

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
