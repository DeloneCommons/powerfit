# Springer Nature template provenance

This working copy uses the official Springer Nature `sn-jnl.cls` and
`sn-mathphys-ay.bst` for the CAM author–year submission format.

## Official distribution verified on 2026-11-12

- Publisher landing page: [Springer Nature LaTeX author support](https://www.springernature.com/gp/authors/campaigns/latex-author-support).
- The linked package is labeled **December 2024**; its [official ZIP](https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/18782940/data/v12) was obtained and inspected during the 2026-11-12 submission audit.
- Files are copied byte-for-byte from `sn-article-template/sn-jnl.cls` and
  `sn-article-template/bst/sn-mathphys-ay.bst` in that ZIP, including their
  original line endings, attribution and license headers.

| Repository file | Bytes | SHA-256 |
|---|---:|---|
| `manuscript/sn-jnl.cls` | 55,857 | `36d0c3273a59d48dc6a9c7b080dfa1ec50dc10229d8751568d1f2e490ffa5ecc` |
| `manuscript/sn-mathphys-ay.bst` | 64,023 | `6a2306683997db76b5e58190acea4dac360c742044114f6a923a4380fbab9008` |

The class header identifies `2019/11/18 v0.1`; the bibliography style header
identifies `2024/07/19 v1.1`. These internal identifiers are retained unchanged
and are distinct from the distribution's December 2024 label.

## Changes from the initial CAM import

The initial import used files from the
[`nickhnelsen/springer-nature-latex-template-improved` mirror](https://github.com/nickhnelsen/springer-nature-latex-template-improved).
Comparison against the official ZIP identified modifications in the class,
including caption punctuation, bibliography backreferences, a natbib/hyperref
patch, and theorem/proof formatting. The mirror class has been replaced with
the official class. The bibliography style was already byte-identical and is
unchanged.

Author-name/year bibliography sorting is selected using the style's supported
`@settings` mechanism in `refs.bib`. The master manuscript writes
`\citation{camBibSettings}` directly to its auxiliary file so BibTeX reads this
nonprinting configuration entry without treating it as a missing natbib
reference. Using `\nocite` for the settings key would produce a false undefined
citation warning. Only actually cited research references are printed; the
settings entry is not. No publisher class or bibliography-style internals are
patched.

CAM-specific front matter, declarations, citation commands and continuous
figure/table numbering are configured in the manuscript source. Journal
instructions take precedence over the generic template's example placement
of acknowledgments.

The bundled class and bibliography style retain their upstream license terms;
their inclusion does not change the licensing of the scientific manuscript or
figures.
