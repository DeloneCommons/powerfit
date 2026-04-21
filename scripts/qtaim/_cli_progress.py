"""Shared optional terminal progress helpers for QTAIM CLI scripts.

These utilities intentionally affect only console output. They are used to add
progress bars and status messages without changing any file artifacts produced by
project scripts.
"""

from __future__ import annotations

import sys
from typing import Iterable, TypeVar

try:  # pragma: no cover - optional runtime dependency
    from tqdm.auto import tqdm as _tqdm
except Exception:  # pragma: no cover
    _tqdm = None

T = TypeVar('T')


def tqdm_available() -> bool:
    """Return ``True`` if :mod:`tqdm` is importable at runtime."""
    return _tqdm is not None


def iter_progress(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    desc: str | None = None,
    disable: bool = False,
    unit: str | None = None,
):
    """Wrap an iterable in ``tqdm`` when available.

    When ``tqdm`` is not installed or progress is disabled, the original
    iterable is returned unchanged.
    """
    if disable or _tqdm is None:
        return iterable
    kwargs = {'total': total, 'desc': desc, 'dynamic_ncols': True, 'mininterval': 0.2}
    if unit is not None:
        kwargs['unit'] = unit
    return _tqdm(iterable, **kwargs)


def make_progress_bar(
    *,
    total: int | None = None,
    desc: str | None = None,
    disable: bool = False,
    unit: str | None = None,
):
    """Create a manual ``tqdm`` progress bar, or ``None`` if unavailable."""
    if disable or _tqdm is None:
        return None
    kwargs = {'total': total, 'desc': desc, 'dynamic_ncols': True, 'mininterval': 0.2}
    if unit is not None:
        kwargs['unit'] = unit
    return _tqdm(**kwargs)


def progress_write(message: str, *, stream=None) -> None:
    """Write a status line that coexists cleanly with active progress bars."""
    if stream is None:
        stream = sys.stdout
    if _tqdm is not None:
        _tqdm.write(message, file=stream)
    else:
        print(message, file=stream)
