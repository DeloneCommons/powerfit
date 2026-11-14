# Public research website

The site at **https://delonecommons.github.io/powerfit/** provides a landing page,
one complete HTML article, and the canonical PDF. `manuscript/` remains the
only maintained scientific source. This directory contains presentation,
conversion and validation code, not a second article.

## Build locally

Use Python 3.10+ and Git with history. On Debian 13 or Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  latexml latexmk lmodern poppler-utils \
  texlive-latex-base texlive-latex-recommended texlive-latex-extra \
  texlive-fonts-recommended
python -m venv .venv-site
. .venv-site/bin/activate
python -m pip install -r site/requirements.txt
python site/build.py
python site/validate.py
python -m unittest discover -s site/tests -v
```

Use a complete Git checkout: the build reads commit history for identification.
The canonical PDF command, source-bundle command and scientific commands remain
unchanged; see the [manuscript guide](../manuscript/README.md) and
[reproducibility overview](../docs/reproducibility.md).

`site/build.py` replaces only its owned `build/site/` and `build/site-work/`
directories. It calls the existing PDF build once, copies its PDF, and checks
that every input's SHA-256 remains unchanged. It never executes experiments,
regenerates scientific figures, or refreshes the frozen manifest.

For local reading, run `python -m http.server 8000 --directory build/site` and
open `http://localhost:8000/`. All runtime asset URLs are relative, including
PDF, CSS, SVG and article links. There are no external fonts, runtime scripts,
tracking requests or frontend framework dependencies.

## Architecture and source relationships

| File / output | Role |
|---|---|
| `source.py` | Extract current front matter and generate an article-class wrapper around the original nine section and five appendix inputs. |
| `build.py` | Run the canonical PDF build and LaTeXML, convert committed PDF figures with Poppler, record provenance, assemble and validate. |
| `render.py`, `site.css` | Add landing-page context, navigation, responsive typography, source identification and archival notices. The abstract is taken from the converted article. |
| `validate.py` | Check scientific structure, source prose, PDF numbering, converter-to-page content, math, bibliography, links and the public asset allowlist. |
| `tests/` | Mutate real built output to prove that scientific omissions and corruptions fail validation; test generated wrapper behavior. |
| `browser_check.py` | Exercise the real assembled site at desktop/phone widths under `/powerfit/` and save screenshots. |
| `build/site-work/` | Ignored wrapper, copied inputs, canonical `.aux`/`.bbl`, converter XML/HTML and logs. Never published. |
| `build/site/` | Only `index.html`, `article.html`, `site.css`, `manuscript.pdf`, seven SVGs, `LICENSE.txt` and `provenance.json`. |
| `build/site-reports/` | Browser captures and machine-readable QA report. Review artifact only. |

The wrapper is regenerated on every build. Title, author, affiliation, email,
abstract, keywords, classification, acknowledgments, declarations and includes
come from `manuscript/manuscript.tex`. The section/appendix files are copied
without modification. The bibliography is the freshly built
`manuscript/manuscript.bbl`, using the existing pinned Springer Nature style;
there is no independently maintained HTML bibliography.

Only publisher/page-layout machinery changes in the wrapper: `sn-jnl` becomes
`article`, the title-page minipage and print spacing are removed, `Needspace`
is a no-op, and the publisher's bibliography containers become neutral
containers. Original independently numbered formal environments and continuous
equation/figure/table numbers are retained. Unsupported front-matter commands and duplicate author/affiliation fields fail
rather than silently producing empty or truncated metadata.

The seven SVGs are direct `pdftocairo -svg` conversions of the committed vector
PDF illustrations. No scientific plot is recomputed or redrawn. Captions remain
in the HTML, images have caption-derived alternative text, and each figure
links to its full-size SVG. The SVGs use vector paths, including outlined text;
accessible descriptions are supplied by the HTML captions, not SVG text
extraction. Wide equations and tables scroll within their own keyboard-focusable
regions on narrow screens. Prose never requires horizontal page scrolling.

`provenance.json` records the checked-out build commit, whether the working tree
was dirty, the latest authored-manuscript commit/date, all source hashes, the
PDF hash, the PDF-to-SVG mapping and converter version. The revision date is
source-history metadata, not a submission or acceptance date. On pull requests
the build commit can be GitHub's tested merge commit. The HTML and PDF are built
from that same checkout. See [archive semantics](../docs/archives.md).

## Converter evaluation

The evaluation used the complete manuscript at
`f4010fcb967767b4263a465ad2a2eb92d1b1458f`, including all appendices and the
fresh canonical bibliography. Tools were make4ht 0.4c / TeX4ht with TeX Live
2024 and LaTeXML 0.8.8. Trials ran on the original Springer entry point and an
article-class wrapper with unchanged section/appendix inputs.

| Approach | Observed result on this manuscript | Decision |
|---|---|---|
| make4ht, original `sn-jnl` | Produced a single HTML document and MathML with the sections and bibliography. Default graphics processing selected PNGs. Three `shortstack` table-heading fallbacks requested bitmap images (`dvipng` was absent in the trial), leaving unresolved heading assets. | Viable with additional TeX4ht configuration, but the default output needs more work to eliminate raster fallbacks and adapt publication markup. |
| make4ht, article wrapper | Same three table-heading bitmap fallbacks and default PNG illustrations. Changing the class alone did not remove these fallbacks. | Not selected. |
| LaTeXML, original `sn-jnl` | No class binding; seven undefined macros (publisher front matter plus `Needspace`), missing class/package bindings and warnings. | Do not convert the publisher wrapper directly. |
| LaTeXML, generated article wrapper | Structured sections, appendices, formal statements/proofs, author–year citations, multi-line table headings and native MathML. Neutralizing `Needspace` and unwrapping the title-page minipage removed conversion/schema errors. | **Selected**, with the existing BibTeX output and separately converted SVGs. |

Representative evaluation commands, run in disposable copies of `manuscript/`:

```bash
make4ht -u -f html5 manuscript.tex 'mathml'
make4ht -u -f html5 article.tex 'mathml'
latexml --dest=manuscript.xml manuscript.tex
latexml --dest=article.xml article.tex
latexmlpost --format=html5 --nosplit --pmml --mathtex \
  --nographicimages --dest=article.html article.xml
```

The generated `article.tex` is retained in `build/site-work/` for inspection.
A successful exit alone is not accepted: unexpected warnings, errors, missing
files/macros, unresolved references, invalid intermediate XML, missing content
or numbering differences fail the build. The site build uses no TeX4ht runtime
dependency; make4ht was an evaluation candidate.

### Known conversion limits

LaTeXML 0.8.8 reports **13 `Warning:not_parsed` mathematical grammar notices**
on this manuscript. They concern semantic interpretation of some mathematical
expressions, not undefined commands or failed presentation rendering. The
selected output is **Presentation MathML with original TeX annotations**, not
Content MathML or a claim of computer-algebra interpretation. Those notices are
retained in `conversion.log`; other warning classes and all errors are fatal.
Representative affected boxed/aligned, norm, Laplacian and clearance formulas
must also be inspected visually when changing converter versions.

LaTeXML 0.8.8 omits the TeX annotation for the literal formula `0` because it
treats that string as false. Assembly adds that annotation for the two affected
formulas, preserving their existing MathML. All 710 displayed/inline MathML
nodes are checked against their converter source strings. The intermediate
XML also contains duplicate list captions and unused aligned-equation fallback
branches; those are not additional formulas to publish.

Modern Chromium, Firefox and Safari support native MathML. Older browsers and
assistive technologies may differ in mathematical rendering and navigation;
the PDF is an additional reading format. The HTML preserves article content
and numbering, not the Springer page layout or PDF page numbers. Browsers'
print output is not the canonical downloadable PDF.

## Validation and browser inspection

The validator independently checks the 128 source labels against the canonical
PDF `.aux`, including all equation, section, appendix, figure, table and formal
statement numbers. It requires equations (1)–(75), nine main sections, five
appendices, seven figures, four numbered tables, three propositions, one
corollary, five proofs and 34 bibliography entries. The unnumbered algorithm
summary table in Appendix D is preserved as well.

Every converter element with an ID is compared with the assembled article,
covering paragraphs, table cells, formal environments and mathematical text.
Long literal prose spans from all 15 authored TeX files are independently
checked against visible HTML (545 spans for this revision). TeX annotations do
not count as visible prose. This is a content-loss guard, not a formal proof
that arbitrary future LaTeX constructs are correctly converted. New structures
or changed inventories require deliberate review of the checks.

Mutation tests remove an appendix, proof, equation, paragraph, formula, figure,
table or bibliography entry; corrupt an equation number or table cell; break a
reference or base-path URL; redirect a citation to the wrong existing entry; swap a figure; alter the PDF; or add an unapproved
file. A separate mutation removes prose from both converter output and the
assembled page, proving the source-prose check is independent.

For browser QA:

```bash
python -m pip install -r site/requirements-browser.txt
python -m playwright install chromium
python site/browser_check.py
```

To use an existing Chromium executable, set `POWERFIT_BROWSER` to its path.
CI installs the Playwright browser and system dependencies. Checks use 1440,
390 and 320 px viewports, `/powerfit/` URLs, actual TOC/equation/citation clicks,
MathML dimensions, all seven loaded SVGs, the PDF response and page overflow.
They reject browser errors and unexpected external runtime requests. Screenshots
cover the landing page, article front matter, Section 4, clearance equations,
Appendices C/D and Table 4. Inspect the images as well as the JSON report.

## Actions and GitHub Pages configuration

[`.github/workflows/site.yml`](../.github/workflows/site.yml) builds and validates
on every pull request, `main` push and manual workflow dispatch. A separate job
deploys only successful builds on `main`, never pull requests or dispatches on
other branches. It uses `actions/upload-pages-artifact@v3`,
`actions/configure-pages@v5` and `actions/deploy-pages@v4`, with deployment-only
`pages: write` and `id-token: write` permissions and the `github-pages`
environment. Scientific experiments are not part of this workflow.

The existing [repro-smoke workflow](../.github/workflows/repro-smoke.yml) and
required `smoke` branch check remain unchanged. Its source/PDF/archive checks
continue independently. Review artifacts include logs and browser screenshots;
**the Pages artifact contains only `build/site/`**.

Repository settings were inspected on 2026-11-14: Pages already reports
`build_type: workflow`, HTTPS enforced, and the intended project URL. No
settings were changed and this PR does not claim a deployment. To configure a
new or reset repository, or verify the existing configuration:

1. Open **Settings → Pages → Build and deployment → Source** and select
   **GitHub Actions** (not a branch/folder publisher).
2. In **Settings → Environments → github-pages**, permit deployment from
   `main`. Keep any required reviewers or other existing protections.
3. Keep the required `smoke` check and existing branch protection unchanged.
   Ensure Actions are enabled for the repository.
4. After merging this PR, inspect the **research-site** workflow's build and
   deploy jobs. If needed, use **Run workflow** on `main`.
5. Confirm the deployment URL, then check `/powerfit/`, `article.html`,
   `manuscript.pdf` and figure links. A successful PR artifact is not evidence
   of a production deployment.

No tag, GitHub Release, journal submission or Zenodo deposit is created by this
workflow. The immutable v2.0.0 DOI is never presented as the DOI of the live
manuscript.
