# External software

This directory stores the exact third-party binary artifacts pinned by the paper
snapshot. The fast repository audit (`python scripts/check_repo_consistency.py`)
verifies the recorded SHA256 digests of the bundled `pyvoro2` wheel and
`Multiwfn_noGUI` executable against the immutable manifest files in this
directory.

## Included artifacts

- `pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl`
  - stable repository-local wheel filename used by the archived reruns.
- `pyvoro2-version.txt`
  - immutable manifest describing the selected pyvoro2 artifact, its provenance,
    digest, and citation metadata.
- `Multiwfn_noGUI`
  - pinned **noGUI / no-drawings** Linux executable used for the QTAIM helper
    workflow.
- `settings.ini`
  - bundled Multiwfn settings file shipped with the selected noGUI package.
- `Multiwfn_LICENSE.txt`
  - license text from the selected Multiwfn package.
- `How_to_cite_Multiwfn.pdf`
  - citation guidance shipped with the selected Multiwfn package.
- `multiwfn-version.txt`
  - immutable manifest describing the selected Multiwfn artifact, digest,
    version, and variant.

## Why the Multiwfn binary is included here

The Multiwfn download site surfaces only the latest package conveniently, which
makes exact binary provenance easy to lose over time. This repository therefore
pins the exact noGUI executable used by the QTAIM helper workflow together with
its digest and license text.

## Platform note

The bundled `pyvoro2` wheel and `Multiwfn_noGUI` binary are Linux artifacts.
If you are not on Linux / WSL2, use the same upstream versions through your
local platform-specific installation route.

## Citation note

If Multiwfn is used in downstream work, follow the citation instructions
shipped in the selected package and reproduced in `Multiwfn_LICENSE.txt` and
the bundled `How_to_cite_Multiwfn.pdf` file.
## License scope

These files are bundled for reproducibility, but they are **not** relicensed
by the root MIT [LICENSE](../LICENSE). The repository-level scope split is
documented in [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md). In
particular:

- the pinned `pyvoro2` wheel remains under `LGPL-3.0-or-later` as recorded in
  `pyvoro2-version.txt`;
- the bundled Multiwfn package remains under the terms shipped in
  `Multiwfn_LICENSE.txt` and the upstream package materials.

If you redistribute this archive, keep those notices with the corresponding
artifacts.
