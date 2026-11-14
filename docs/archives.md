# Archives, manuscript revisions and citation

The live manuscript and the published archives have different identities.
The website's HTML and PDF are generated together from the LaTeX sources at
one Git commit. They describe an **author manuscript submitted for peer review**
to *Computational and Applied Mathematics*, not an accepted or published article.
No journal publication DOI is claimed.

## Versions

| Record | Meaning |
|---|---|
| Current `main` | The evolving author manuscript; use the website's generated revision date and source commit to identify the displayed version. |
| Original CAM synchronization baseline | PR #7 at `f4010fcb967767b4263a465ad2a2eb92d1b1458f` on 2026-11-14. This historical reference does not identify subsequent manuscript revisions. |
| [v2.0.0](https://doi.org/10.5281/zenodo.24047266) | A published, immutable archive containing the earlier revised article and reproducibility infrastructure. Its manuscript is **not identical to the current live HTML/PDF**. |
| [v1.0.0](https://doi.org/10.5281/zenodo.19673558) | The original published scientific evidence and historical manuscript. |
| [Concept DOI](https://doi.org/10.5281/zenodo.19673557) | The family of published powerfit versions; it does not assign a DOI to every Git commit. |
| [pyvoro2 0.6.3](https://doi.org/10.5281/zenodo.19143984) | The separately archived fitting software used for the reported calculations. |

The website displays the last authored-manuscript change date and commit,
plus the website source commit. Its `provenance.json` records source, PDF and
figure hashes. A local build with uncommitted changes is explicitly marked;
its Git commit alone does not identify those changes. The revision date is
source-history metadata, not a claimed submission or acceptance date.
See [CAM synchronization](../manuscript/CAM_SYNC.md) and the unchanged
[historical v2.0.0 release note](release-v2.0.0.md).

## Frozen scientific evidence


The v2.0.0 article revised the mathematics and interpretation while retaining
the original experimental evidence. The website work does not revise that science. **989 files** under `experiments/`,
`results/`, `data/`, `environments/`, `external_software/`, `scripts/qtaim/`,
and the shared `scripts/_figure_io.py` remain byte-identical to
`80933a14c57d4766bd2c03b2990d949a452031fc` (`v1.0.0`).

Their historical READMEs, registry entries and source comments are frozen too:
old manuscript numbers, paths and commands describe v1.0.0. Use the current
guides for maintained commands. Retired manuscript-only generators are available in
the [v1.0.0 source](https://github.com/DeloneCommons/powerfit/tree/v1.0.0);
the experimental algorithms, postprocessing and shared scientific helpers remain
here because they are needed to understand or repeat the original calculations.

### Frozen records and the current manuscript

| Experiments | Current placement | Archived protocol |
|---|---|---|
| A / C / D: recovery, missing data, feasibility | Section 6.1; Appendix D.3.1 | [A](../experiments/registry/A_exact_recovery.md), [C](../experiments/registry/C_missing_data.md), [D](../experiments/registry/D_infeasible_constraints.md) |
| B: noise and outliers | Section 6.1; Appendix D.3.2 | [B](../experiments/registry/B_noise_robustness.md) |
| F: periodic images | Section 6.2; Appendix D.3.3 | [F](../experiments/registry/F_periodic_cases.md) |
| G: structured mismatch | Section 6.2; Appendix D.3.4 | [G](../experiments/registry/G_model_mismatch.md) |
| E / H: refinement | Section 6.3; Appendix D.3.4 | [E](../experiments/registry/E_active_set.md), [H](../experiments/registry/H_supergraph_mismatch.md) |
| J: molecular fitting and diagnostics | Section 7; Appendix E | [J](../experiments/registry/J_qtaim_molecular.md) |

## Citation and licenses


| Resource | Persistent identifier |
|---|---|
| `powerfit` v2.0.0 release | [10.5281/zenodo.24047266](https://doi.org/10.5281/zenodo.24047266), the version DOI. |
| Evolving `powerfit` project | [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557), the all-versions concept DOI. |
| Frozen `powerfit` v1.0.0 evidence | [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558). |
| Fitting software `pyvoro2` 0.6.3 | [10.5281/zenodo.19143984](https://doi.org/10.5281/zenodo.19143984). |

[CITATION.cff](../CITATION.cff) retains the v2.0.0 archive's citation metadata;
its version DOI does not identify the CAM-synchronized `main`. The concept DOI
covers published project versions. See the
[v2.0.0 release notes](release-v2.0.0.md) for the archive contents and
provenance.

The root [LICENSE](../LICENSE) covers first-party materials. Bundled third-party
software retains its upstream terms in
[THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md). The Zenodo archive uses
`Other (Open)` for the mixed-license collection.

When referring to the current author manuscript, give its title, author,
status, displayed revision date and source commit, and link the live article.
For reproducibility evidence, cite the appropriate version-specific archive.
Do not use the v2.0.0 version DOI as the identifier of the live manuscript.
The website introduces no tag, GitHub Release or Zenodo deposit.
