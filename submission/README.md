# Submission

This directory stores generated submission artifacts.

## Subdirectories

- `flat/` — tracked flat source bundle for journal submission.

Regenerate `flat/` with `python scripts/make_submission_bundle.py` whenever
manuscript-side source files change. For the canonical end-to-end manuscript
build, use `bash scripts/build_manuscript_pdfs.sh`; it refreshes the manuscript
side tables and figures, rebuilds `flat/`, and then makes local verification
PDFs. `submission/flat/manuscript.pdf` is only a local verification build
product from that script and is ignored by git. When both PDF and PNG versions
of the same figure exist, the flat bundle keeps the PDF figure copy.

Inside the same locked Python environment recorded under `environments/`, the
manuscript-facing figure PDFs/PNGs that feed the flat bundle are expected to be
byte-identical across rebuilds. The final `submission/flat/manuscript.pdf`
verification build is different: LaTeX may still emit byte-different document
PDFs even when the rendered content is unchanged.
