"""BCRED — Blackstone Private Credit Fund (CIK 0001803498).

Non-listed perpetual BDC. Files standard 10-Q with XBRL SOI; structure
is similar to BXSL (same filer family — Blackstone). Use generic
extraction; tune only if specific quirks emerge.
"""
from __future__ import annotations
from ._base import Bdc
from . import register


@register
class Bcred(Bdc):
    ticker = "BCRED"
    canonical_period = "2026-03-31"
