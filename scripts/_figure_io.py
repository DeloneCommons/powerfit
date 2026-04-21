"""Deterministic Matplotlib figure output helpers.

These helpers are intended to make Python-generated figure assets reproducible
within the same locked Python environment by freezing output metadata and
centralizing save options.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.figure

_FIXED_PDF_METADATA = {
    'Creator': 'powerfit deterministic figure writer',
    'Producer': 'powerfit deterministic figure writer',
    'CreationDate': datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    'ModDate': datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
}

_FIXED_PNG_METADATA = {
    'Software': 'powerfit deterministic figure writer',
    'Creation Time': '2026-01-01T00:00:00Z',
}


def save_figure_pair(
    fig: matplotlib.figure.Figure,
    *,
    png_path: Path | None,
    pdf_path: Path | None,
    title: str,
    png_dpi: int = 300,
    **savefig_kwargs: Any,
) -> None:
    """Save a figure to PNG/PDF with stable metadata.

    Args:
        fig: Figure to save.
        png_path: Output PNG path, or None to skip PNG.
        pdf_path: Output PDF path, or None to skip PDF.
        title: Stable title stored in output metadata.
        png_dpi: DPI to use for PNG output.
        **savefig_kwargs: Common keyword arguments passed to savefig.
    """
    if png_path is None and pdf_path is None:
        raise ValueError('At least one output path must be provided.')

    pdf_metadata = dict(_FIXED_PDF_METADATA)
    pdf_metadata['Title'] = title

    png_metadata = dict(_FIXED_PNG_METADATA)
    png_metadata['Title'] = title

    if png_path is not None:
        png_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            png_path,
            dpi=png_dpi,
            metadata=png_metadata,
            **savefig_kwargs,
        )

    if pdf_path is not None:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            pdf_path,
            metadata=pdf_metadata,
            **savefig_kwargs,
        )


def save_figure(
    fig: matplotlib.figure.Figure,
    outpath: Path,
    *,
    title: str | None = None,
    png_dpi: int = 300,
    save_pdf_sibling: bool = False,
    save_png_sibling: bool = False,
    **savefig_kwargs: Any,
) -> None:
    """Save a figure using the output path suffix to decide the format.

    Args:
        fig: Figure to save.
        outpath: Primary output path. Must end in ``.png`` or ``.pdf``.
        title: Stable title stored in output metadata. Defaults to ``outpath.stem``.
        png_dpi: DPI to use for PNG output.
        save_pdf_sibling: When ``outpath`` ends in ``.png``, also write a PDF
            with the same stem.
        save_png_sibling: When ``outpath`` ends in ``.pdf``, also write a PNG
            with the same stem.
        **savefig_kwargs: Common keyword arguments passed to savefig.
    """
    suffix = outpath.suffix.lower()
    if suffix not in {'.png', '.pdf'}:
        raise ValueError(f'Unsupported figure suffix: {outpath.suffix}')

    png_path: Path | None = None
    pdf_path: Path | None = None
    if suffix == '.png':
        png_path = outpath
        if save_pdf_sibling:
            pdf_path = outpath.with_suffix('.pdf')
    else:
        pdf_path = outpath
        if save_png_sibling:
            png_path = outpath.with_suffix('.png')

    save_figure_pair(
        fig,
        png_path=png_path,
        pdf_path=pdf_path,
        title=title or outpath.stem,
        png_dpi=png_dpi,
        **savefig_kwargs,
    )
