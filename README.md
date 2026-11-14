# powerfit

**Fixed-site inverse fitting of power-diagram weights from pairwise separator data**

Ivan Yu. Chernyshov

How can independently estimated separators between pairs of objects define a
single spatial partition? This work fits a power (Laguerre) diagram at fixed
sites, identifies what the observations determine, and checks which geometric
faces the fitted weights actually support.

**[Read the full article](https://delonecommons.github.io/powerfit/article.html)** ·
**[Download the PDF](https://delonecommons.github.io/powerfit/manuscript.pdf)** ·
**[Reproducibility guide](docs/reproducibility.md)** ·
[Research website](https://delonecommons.github.io/powerfit/)

## The research

Each pairwise separator position specifies a difference of site weights.
Graph conditions characterize exact compatibility and identifiable weight
differences; weighted least squares reconciles inconsistent observations.
A fitted separator need not form a shared cell face. Local membership and
centered clearance assess the geometry independently of fitting error.

Synthetic experiments and an application to 100 molecules illustrate the
method and its limitations: better fitting need not improve agreement with an
independent reference. The molecular study evaluates separator positions and
pair adjacencies, rather than reconstructing complete QTAIM atomic basins.

## Relationship to pyvoro2

The fitting software is maintained separately in
[pyvoro2](https://github.com/DeloneCommons/pyvoro2). **powerfit** contains the
research article, experimental protocols, inputs, results and verification
infrastructure. The reported calculations use
[pyvoro2 0.6.3](https://doi.org/10.5281/zenodo.19143984).

## Explore the repository

| Location | Start here for |
|---|---|
| [manuscript/](manuscript/README.md) | Authoritative LaTeX article, appendices, bibliography, seven figures and PDF/source-bundle commands. |
| [docs/](docs/README.md) | Reproducibility, archive identity and documentation navigation. |
| [site/](site/README.md) | HTML conversion, website validation and GitHub Pages setup. |
| [scripts/](scripts/README.md) | Established build/check commands and scientific rerun workflows; molecular tools remain in `scripts/qtaim/`. |
| [experiments/](experiments/README.md) | Frozen synthetic protocols, runners and analyses. |
| [results/](results/README.md) and [data/](data/README.md) | Frozen numerical evidence and molecular inputs. |
| [environments/](environments/README.md) and [external_software/](external_software/README.md) | Archived dependencies and third-party software provenance. |

## Manuscript status and archives

The current article is an **author manuscript submitted for peer review** to
*Computational and Applied Mathematics*. It is **not an accepted or published
journal article**. The CAM source synchronization is recorded in
[manuscript/CAM_SYNC.md](manuscript/CAM_SYNC.md); the current author-manuscript
revision is dated **2026-11-14**, at
[`f4010fcb9677`](https://github.com/DeloneCommons/powerfit/commit/f4010fcb967767b4263a465ad2a2eb92d1b1458f).
The website records the source commit and revision date for each build.

The live HTML/PDF on `main` is **not identical to the published v2.0.0 archive**.
Its PDF and HTML are generated from the same LaTeX sources. The original
**989 SHA-256-protected scientific files** remain unchanged.

| Published record | DOI |
|---|---|
| powerfit v2.0.0 archive | [10.5281/zenodo.24047266](https://doi.org/10.5281/zenodo.24047266) |
| powerfit v1.0.0 scientific evidence | [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558) |
| powerfit concept DOI, covering published versions | [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557) |

[CITATION.cff](CITATION.cff) retains the v2.0.0 archive's citation metadata.
Its DOI does not identify the current manuscript; no journal publication DOI
is claimed. See [archives and citation guidance](docs/archives.md) and the
[historical release note](docs/release-v2.0.0.md).

First-party materials use the [MIT license](LICENSE). Bundled third-party
materials retain their [upstream terms](THIRD_PARTY_LICENSES.md); the Zenodo
collection uses `Other (Open)` for this license mixture.

## Build or verify

Start with the [reproducibility overview](docs/reproducibility.md). It preserves
the PDF, source-bundle, figure/table verification, environment setup and
scientific-rerun instructions. The [documentation index](docs/README.md) links
the detailed guides; [CI documentation](.github/workflows/README.md) describes
the independent scientific and website checks.
