"""Per-BDC extraction modules.

Each module defines a `Bdc` subclass with filer-specific tuning. The
generic extractor (extract_bdc_soi.py) imports `get(ticker)` from here
to dispatch.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import Bdc

if TYPE_CHECKING:
    pass


_REGISTRY: dict[str, type[Bdc]] = {}


def register(cls: type[Bdc]) -> type[Bdc]:
    _REGISTRY[cls.ticker.upper()] = cls
    return cls


def get(ticker: str) -> Bdc:
    """Return an instantiated Bdc handler for `ticker`. Falls back to a
    generic Bdc if no designated module is registered."""
    ticker = ticker.upper()
    # Lazy-import so adding a new bdcs/<ticker>.py file Just Works
    if ticker not in _REGISTRY:
        try:
            __import__(f"bdcs.{ticker.lower()}")
        except ImportError:
            pass
    cls = _REGISTRY.get(ticker)
    if cls is None:
        # Generic fallback
        return Bdc(ticker=ticker)
    return cls()


def known() -> list[str]:
    """Tickers with a designated module loaded."""
    return sorted(_REGISTRY)
