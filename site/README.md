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
PDF, CSS, JavaScript, SVG and article links. There are no external fonts,
external runtime requests, tracking or frontend framework dependencies.

The compact **Theme** selector offers System (the default), Light and Dark.
System follows the OS preference, including changes while reading. Explicit
Light/Dark choices are stored locally under `powerfit-theme` and apply to both
pages and reloads; choosing System removes that override. If browser storage
is blocked, selection still works for the current page. The local `site.js`
applies the preference before CSS paints. Without JavaScript, CSS follows the
OS and the unavailable selector stays hidden. All scientific SVG illustrations
retain a white background and their original colors in both themes.

The article contents start collapsed at widths up to 760 px and open on wider
screens. The native disclosure remains keyboard accessible; opening it exposes
subsections on mobile too. Without JavaScript, the contents stay open.

## Architecture and source relationships

| File / output | Role |
|---|---|
| `source.py`, `texsyntax.py` | Consume supported Springer front matter and preamble, then generate a wrapper around the original active inputs; reject unsupported content instead of dropping it. |
| `inventory.py`, `mathsyntax.py`, `coverage.py` | Walk original authored inputs in order and match supported prose, structure, math, tables, figures and references to XML, raw HTML and the assembled page. |
| `canonical.py`, `scientific.py` | Read fresh canonical labels, recorder and bibliography evidence; locate the separately reviewed mathematical role checks by source identity. |
| `build.py` | Run the canonical PDF build and LaTeXML, convert committed PDF figures with Poppler, record provenance, assemble and validate. |
| `render.py`, `site.css`, `site.js` | Add landing-page context, navigation, responsive typography, theme preferences, source identification and archival notices. The abstract is taken from the converted article. |
| `validate.py`, `mathml.py`, `bibliography.py` | Check scientific structure, source prose, PDF numbering, converter-to-page text and Presentation MathML trees, bibliography DOIs against `refs.bib`, links and the public asset allowlist. |
| `conversion_warnings.py`, `reviewed-math-warnings.json` | Parse complete diagnostics and apply finite, source-bound approvals with converter and binding identities. |
| `tests/` | Mutate real built output to prove that scientific omissions and corruptions fail validation; test generated wrapper behavior. |
| `browser_check.py` | Exercise the real assembled site at desktop/phone widths under `/powerfit/` and save screenshots. |
| `build/site-work/` | Ignored wrapper, copied inputs, canonical `.aux`/`.bbl`/`.fls`, XML/raw HTML, source/validation/warning reports, tool versions and logs. Never published. |
| `build/site/` | Only `index.html`, `article.html`, `site.css`, `site.js`, `manuscript.pdf`, source-mapped SVGs, `LICENSE.txt` and `provenance.json`. The public asset allowlist excludes review evidence. |
| `build/site-reports/` | Browser captures and machine-readable QA report. Review artifact only. |

The wrapper is regenerated on every build. Title, author, affiliation, email,
abstract, keywords, classification, acknowledgments, declarations and includes
come from `manuscript/manuscript.tex`. The section/appendix files are copied
without modification. Only recursively active literal inputs contribute authored
content; an orphan `.tex` file is not activated by a directory glob. The
bibliography is the freshly built
`manuscript/manuscript.bbl`, using the existing pinned Springer Nature style;
there is no independently maintained HTML bibliography.

Conversion uses `latexml --nocomments`. LaTeXML normally injects source-location
comments every 25 lines. With Springer's `\doiurl` macro expanding into `\url`,
those comments leaked into three DOI link URLs and their displayed text in the
initial website conversion. Disabling comment injection fixes the conversion
generically; neither `refs.bib` nor the generated `.bbl` is rewritten. Every
rendered bibliography DOI is independently checked by citation key against the
authoritative literal DOI field in `refs.bib`, including presence, destination
and displayed URL. DOI URLs elsewhere on the site are also checked for malformed
syntax. These checks are offline and do not depend on DOI resolver availability.
Unsupported DOI metadata expressions fail for review instead of being guessed.
The bounded BibTeX scanner reads field boundaries independently of line layout,
including complete single-line entries and a DOI following another field on the
same line. Balanced braces and quoted values protect embedded commas;
text mentioning `doi` inside another field is not treated as a DOI field.
Backslashes do not escape structural braces or quotes at the BibTeX parsing
layer. The scanner therefore counts those delimiters even after a backslash,
so an unrelated field cannot consume and conceal a following DOI. Regression
tests include the audited escaped-delimiter record, its actual Springer BibTeX
output, and rejection of a rendered entry that omits its DOI.
DOIs must be single braced or quoted literals. Macros, concatenations, duplicate
DOI fields and malformed expressions fail explicitly. `crossref` inheritance is
unsupported and fails explicitly rather than silently losing an inherited DOI;
the current bibliography does not use it. This is not a general
BibTeX evaluator; the canonical BibTeX build still processes the bibliography.

The adapter consumes every replaced front-matter token and requires exactly one
value for title, author, email, affiliation, abstract, keywords and classification.
Visible text or unknown commands before `\maketitle`, unsupported scientific
preamble macros/packages/options, and ambiguous metadata fail with a diagnostic.
The explicit publisher/extraction allowlist and balanced `\newtheorem` support
live in `source.py`; adding a new scientific macro requires a focused syntax and
conversion-support change.

Only publisher/page-layout machinery changes in the wrapper: `sn-jnl` becomes
`article`, the recognized opening title-page minipage/font/spacing idiom is
adapted without stripping later scientific layout, `Needspace`
is a no-op, and the publisher's bibliography containers become neutral
containers. Original independently numbered formal environments and continuous
equation/figure/table numbers are retained. The opening layout adapter does not
assume that the first body input lives under `sections/`.
The classification heading comes from the optional argument of `\pacs`, rather
than a fixed `MSC2020` label. One explicit literal label is supported (letters,
digits, spaces, periods, parentheses, `/` and `-`); omitted, empty, duplicate or
macro-based labels fail for review. The classification value, supported author
metadata and declarations continue to come from the authoritative source.

Paragraph heading levels follow their actual enclosing section heading. For
example, a paragraph under a subsection uses `h4` even if LaTeXML reserved `h4`
for an absent subsubsection. Heading classes, text, anchors and CSS presentation
are preserved; the validator and browser checks reject skipped heading levels.

The original seven SVGs are direct `pdftocairo -svg` conversions of the committed vector
PDF illustrations. No scientific plot is recomputed or redrawn. Captions remain
in the HTML, images have caption-derived alternative text, and each figure
links to its full-size SVG. The SVGs use vector paths, including outlined text;
accessible descriptions are supplied by the HTML captions, not SVG text
extraction. Additional supported source graphics receive the same conversion
and source-to-asset checks. Distinct sources with the same output basename fail
before conversion, preserving existing URLs without silent overwrites.
Wide equations and tables scroll within their own keyboard-focusable
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
latexml --nocomments --dest=article.xml article.tex
latexmlpost --format=html5 --nosplit --pmml --mathtex \
  --nographicimages --dest=article.html article.xml
```

The generated `article.tex` is retained in `build/site-work/` for inspection.
A successful exit alone is not accepted: unexpected warnings, errors, missing
files/macros, unresolved references, invalid intermediate XML, missing content
or numbering differences fail the build. The site build uses no TeX4ht runtime
dependency; make4ht was an evaluation candidate.

### Known conversion limits

At the reviewed baseline `09650f83c85549a7f168c61bcdc5ff68ab019e43`,
LaTeXML 0.8.8 emitted 13 `Warning:not_parsed` notices. This is a dated observation,
not a required warning total. Presentation MathML and original TeX annotations
are preserved; semantic-parser notices do not establish symbolic equivalence.

The active policy is [`reviewed-math-warnings.json`](reviewed-math-warnings.json).
Each approval records the complete reviewed source expression and environment,
its fingerprint and macro context, a review reference/rationale, and finite
per-role occurrence caps. Roles bind the complete diagnostic signature, rule,
`In` expression and token trace. The policy also pins the conversion stage,
LaTeXML version and hashes of relevant core/binding files. The console and rich
`article.latexml.log` diagnostics must reconcile, including completion summaries;
unparsed or incomplete diagnostic blocks cannot hide a new warning.

Source coordinates help attribute a warning to one expression; they do not
approve it. Harmless line movement, comments, supported reflow and label-only
renames retain source identity. Matching must be unique, including explicitly
reviewed locationless roles. A changed expression that still emits an old
warning, an ambiguous match, a new role, excess occurrences, macro-context drift
or converter/binding drift fails. A resolved warning may disappear, and an
unused approval does not require recreating that warning. Postprocessing has no
warning allowance.

On a warning failure inspect `warning-matches.json`, both converter logs, the
complete current source expression and its rendered math. The report contains
diagnostic/source candidates for review; it never rewrites approvals. Approve a
policy change only after that review, updating the rationale, exact identity and
finite role caps. Do not regenerate approvals from the new log or add broad
message/category suppressions. Converter upgrades require binding/version and
presentation review even if no warnings remain.

LaTeXML 0.8.8 omits the TeX annotation for the literal formula `0` because it
treats that string as false. Assembly repairs that narrow annotation case with
unchanged presentation children. All supported mathematical occurrences are
checked against original source inventory and converter annotations. Duplicate
list captions and unused aligned-equation fallback branches are classified
explicitly rather than counted as additional published formulas.

Modern Chromium, Firefox and Safari support native MathML. Older browsers and
assistive technologies may differ in mathematical rendering and navigation;
the PDF is an additional reading format. The HTML preserves article content
and numbering, not the Springer page layout or PDF page numbers. Browsers'
print output is not the canonical downloadable PDF.

**Boxed emphasis (O1, deferred):** Chromium does not draw the border for the
article's twelve `menclose notation="box"` expressions, including equation (41).
The expression, enclosure element and children remain intact; the canonical
Springer PDF shows the intended boxes. A disposable rendering probe confirmed
that a CSS border draws a box in Chromium, but CSS has no native-enclosure
capability query. An unconditional border risks a second box in browsers with
native enclosure support. Reliable conditional rendering detection and coverage
of those browsers are deferred rather than added to this focused correction.

## Validation and browser inspection

`source-inventory.json` is read from the original Springer master and recursive
literal active inputs before the generated website wrapper is evidence. The
bounded grammar handles comments, escaped delimiters, balanced arguments,
section hierarchy/appendices, formal statements and short proofs, figures and
captions, tables including unnumbered `tabular`, inline math and supported
displays. Numbered rows account for `align`, `\notag`/`\nonumber` and supported
nested `aligned`/`cases` structures. Labels are optional; unlabelled objects keep
their source file, owner, order, content and multiplicity. Unknown content-bearing
constructs fail rather than being approximated by a general TeX interpreter.
See the explicit command/environment/token sets in `inventory.py` and
`mathsyntax.py` when extending the grammar.

Literal input expansion preserves TeX's physical endline and comment semantics,
including files without a final LF. Control-word boundaries survive input and
comment expansion; delimiter scans consume whole control sequences, so an
alignment row break followed by `]` is not a display terminator. Small lexical
fixtures are cross-checked by actual TeX compilation.

Supported statement declarations are literal `\newtheorem{name}{Heading}`
with separate global counters. Shared/section counters, custom list markers,
alternate short captions/headings, content-inserting column specifications and
unmapped statement environments fail explicitly. Tables support the checked
`l`/`c`/`r`/literal-width `p` columns, empty intercolumn spacing and bounded
layout commands. `\citep`, `\citet`, `\ref` and `\eqref` have explicit mappings.
Source table cells require an effective unit grid in XML and both HTML stages:
absent spans and explicit `1` are accepted; all other span values fail. Authored
`\multicolumn`/`\multirow` remain unsupported and would need an explicit source
grid model. Generated equation-layout spans are outside this restriction.
New converter projections, such as math consisting solely of text, need an
explicit representation rule before they can pass source coverage.

Coverage matches each supported source object within its containing block to
XML, raw HTML and final HTML. It checks prose and short declarations, mathematical
tokens/roles, row order, table-cell content, captions, source graphics and
citation/reference destinations. Equal global counts cannot satisfy missing or
substituted content. TeX annotations and text elsewhere in the article cannot
stand in for missing visible prose. `source-validation.json` records the matches,
errors, source hashes and validated browser targets; it is a build review record,
not a second maintained scientific source.

Source labels are bound to independently matched owners, including equation
rows; equal numbers on different objects do not make labels interchangeable.
Visible section/float/statement identities use source counters and theorem
headings. Rendered reference numbers use the canonical auxiliary records, and
named source anchors must sit at the corresponding visible destination. Hidden
content cannot satisfy the ordered source comparison.

Every equation, including unlabelled and unnumbered displays, has a matched
source owner and an expected number or explicit absence of numbering in each
representation. Alignment rows retain ordered scientific cells within that
owner, including supported nested non-numbering environments. Moving numbers
between equations or moving cells across row boundaries fails even when the
flattened math and global number sequence are unchanged. Layout padding is
transparent; scientific row wrappers and number cells must remain visible.
After independent content matching, equation destinations must bind the same
source owner across XML and HTML, preventing swapped IDs from redirecting
references while leaving all visible equation text unchanged.

Equation projection also checks the entire surrounding layout for unconsumed
content. Every scientific cell/Math leaf must belong to the consumed source
projection; only the explicit MathFork fallback is exempt. Padding may contain
whitespace and empty `span`/`br` scaffolding, never prose or mathematics. Number
cells permit the checked numbering tag and empty layout only. Wrapper text,
child tails, extra cells and unsupported metadata/projections fail with an
`Unexpected equation content` diagnostic, even if all three products agree.

Fresh canonical evidence has separate roles: balanced `.aux` records confirm
source-label membership and numbering; `.fls` confirms which local inputs the
canonical compiler consumed, with explicit Unicode-support/generated/system
roles; `.bbl` confirms bibliography keys, order, multiplicity and full formatted
entry text, including authors and titles. The formatted-bibliography reader
accepts explicit Springer containers, known field/formatting wrappers, literal
URLs and supported accents; unknown item commands fail instead of disappearing.
Aux labels are not treated as a full
inventory of numbered equations. Literal DOI expectations still come separately
from `refs.bib`. The canonical build and converter share sources and the `.bbl`,
so these layers have complementary roles rather than supplying a universal proof
of scientific equivalence.

Fresh natbib `\bibcite` records in the canonical `.aux` independently constrain
visible citation authors, years, linked year text, grouping and literal notes in
raw and final HTML. The bounded mapping supports `\citep`/`\citet`, ordered key
groups, adjacent repeated authors and literal four-digit years with optional
lowercase suffixes. It is not a general natbib interpreter: numeric/starred
forms, duplicate keys within a group, macro-bearing notes, unknown author
commands and nonliteral years fail explicitly. Expected attribution never comes
from the LaTeXML citation display. Canonical PDF first-page identity comparisons
use whole field tokens and exact email boundaries while tolerating supported
wrapping, hyphenation, ligatures and author footnote markers.

Every converter element with an ID is compared with the assembled article.
Presentation MathML parity preserves element names, hierarchy, child/token order
and attributes, including scripts, fractions, radicals, limits and alignment.
Only attribute order, comments and non-token indentation are ignored. The
non-rendered `semantics` wrapper and annotations are separated from presentation;
the literal-`0` annotation repair requires unchanged presentation children.

The separately reviewed scientific predicates in `scientific.py` check the
reduced spectral bound's half powers and square-root denominators, the
measurement-error energy's sum limits and squared norm, and the connector
clearance's minimum constraints followed by a fraction. They resolve source
labels or one uniquely matching unchanged expression, then join to generated
IDs. Equation renumbering and an unambiguous label-only rename need no scientific
expectation rewrite. Changing or removing a reviewed formula requires scientific
review; the predicates are not automatically learned from changed source.
These checks cover selected mathematical roles, not symbolic equivalence.

The four frozen numerical table recipes are independently checked by
`scripts/check_manuscript_tables.py`, which locates their labels in the active
source graph instead of fixed filenames. The original seven approved figure
identities retain independent reconstruction/provenance checks. These reviewed
scientific obligations are separate from current manuscript-wide object totals;
additional supported sections, equations, tables, figures and references do not
require replacing unrelated count snapshots.

Small explicit fixtures and mutation tests exercise positive revisions and
common omissions from converter and final output together. They also test
short-proof ownership, wrong mathematical roles/annotations, reordered or
substituted content, reference destinations, bibliography author/title loss and
multiplicity, unsupported syntax, asset collisions and finite warning review.
Existing PDF, provenance, asset, native MathML and DOI checks remain active.

For browser QA:

```bash
python -m pip install -r site/requirements-browser.txt
python -m playwright install chromium
python site/browser_check.py
```

To use an existing Chromium executable, set `POWERFIT_BROWSER` to its path.
CI installs the Playwright browser and system dependencies. Checks use 1440,
390 and 320 px viewports and `/powerfit/` URLs. At each size they exercise System,
Light and Dark, live OS changes, explicit overrides, cross-page/reload persistence,
keyboard focus, mobile contents disclosure, actual TOC/equation/citation clicks,
MathML dimensions, all validated source-mapped SVGs, the PDF response and page overflow.
Contrast checks cover text, links, controls, focus rings, mathematics and tables;
figures must remain white and uninverted. CSS-only OS preference is checked with
JavaScript disabled; storage denial and white print backgrounds are checked too.
Browser errors and external runtime requests fail QA.
Browser expectations are loaded from the successful schema-1
`source-validation.json`, including the final article SHA-256. Missing, invalid
or stale reports fail before browser checks. Counts, navigation destinations and
capture targets therefore come from validated mappings rather than current
LaTeXML-generated anchor snapshots. Screenshots in **both Light and Dark at all
three widths** cover both pages, source-mapped structural targets, the reviewed
mathematical expressions and a scientific figure. Inspect the images and
`build/site-reports/browser.json` together; browser layout tests supplement
independent scientific-content validation.

## Actions and GitHub Pages configuration

[`.github/workflows/site.yml`](../.github/workflows/site.yml) builds and validates
on every pull request, `main` push and manual workflow dispatch. A separate job
deploys only successful builds on `main`, never pull requests or dispatches on
other branches. It uses `actions/upload-pages-artifact@v3`,
`actions/configure-pages@v5` and `actions/deploy-pages@v4`, with deployment-only
`pages: write` and `id-token: write` permissions and the `github-pages`
environment. Scientific experiments are not part of this workflow.

The [repro-smoke workflow](../.github/workflows/repro-smoke.yml) retains the
required `smoke` name and scientific/source/PDF/archive responsibilities;
`build` remains the separately required site check. Neither check is bypassed
by manuscript path filters. Smoke's first-page CAM check derives supported front
metadata and opening declaration prose from source, without current MSC/ORCID
or manuscript-wide bibliography page-string sentinels.

`scripts/check_repo_consistency.py` authenticates the frozen manifest's raw bytes
against its independently reviewed SHA-256 identity before reading its entries,
then checks the original 989 protected files. A paired file-and-manifest edit or
entry deletion cannot redefine that baseline. The anchor works without Git
history and is not an automatic manifest-refresh mechanism. Historical archive
metadata and protected scientific evidence remain immutable.

The always-uploaded `research-site-review` artifact retains the existing 14-day
policy and includes the website, screenshots/browser report, logs, generated
`article.tex`, XML/raw HTML, fresh canonical `.aux`/`.bbl`/`.fls`, optional contents
files, `source-inventory.json`, `source-validation.json`, `warning-matches.json`
and `tool-versions.json`. Evidence generated before a failure is retained;
later-stage files may be absent. **The Pages artifact contains only
`build/site/`**, with the existing public-asset allowlist.

Repository settings were inspected on 2026-11-14: Pages already reports
`build_type: workflow`, HTTPS enforced, and the intended project URL. No
settings were changed and this PR does not claim a deployment. To configure a
new or reset repository, or verify the existing configuration:

1. Open **Settings → Pages → Build and deployment → Source** and select
   **GitHub Actions** (not a branch/folder publisher).
2. In **Settings → Environments → github-pages**, permit deployment from
   `main`. Keep any required reviewers or other existing protections.
3. Keep both required `smoke` and `build` checks and existing branch protection
   unchanged.
   Ensure Actions are enabled for the repository.
4. After merging this PR, inspect the **research-site** workflow's build and
   deploy jobs. If needed, use **Run workflow** on `main`.
5. Confirm the deployment URL, then check `/powerfit/`, `article.html`,
   `manuscript.pdf` and figure links. A successful PR artifact is not evidence
   of a production deployment.

No tag, GitHub Release, journal submission or Zenodo deposit is created by this
workflow. The immutable v2.0.0 DOI is never presented as the DOI of the live
manuscript.
