"""Per-BDC HTML SOI parsers.

The XBRL extractor in extract_bdc_soi.py captures structured numeric
facts (FV, cost, rate, spread, PIK). But each BDC's 10-K SOI HTML
table contains additional fields not tagged in XBRL — most importantly
sector groupings (via section-break rows), acquisition date, maturity
date, base-rate name (SOFR/SONIA/Prime), business description, and
footnote markers.

This package holds per-BDC parsers that walk the SOI table HTML and
emit one dict per position. The enrichment step (enrich_soi.py) then
joins these to XBRL positions by issuer + FV to backfill metadata.
"""
from __future__ import annotations

from ._base import SoiHtmlParser, ParsedRow

_REGISTRY: dict[str, type[SoiHtmlParser]] = {}


def register(cls: type[SoiHtmlParser]) -> type[SoiHtmlParser]:
    _REGISTRY[cls.ticker.upper()] = cls
    return cls


def get(ticker: str) -> SoiHtmlParser | None:
    """Return an instantiated parser for `ticker`, or None if no parser
    is registered yet."""
    t = ticker.upper()
    if t not in _REGISTRY:
        try:
            __import__(f"soi_html.{t.lower()}")
        except ImportError:
            return None
    cls = _REGISTRY.get(t)
    return cls() if cls else None


def known() -> list[str]:
    return sorted(_REGISTRY)
