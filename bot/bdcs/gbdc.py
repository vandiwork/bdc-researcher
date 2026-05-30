"""GBDC — Golub Capital BDC, Inc. (CIK 0001476765).

GBDC has a few issuer-level "bare" identifier rows where the FV exceeds
the sum of the leaf tranches (e.g. Chestnut Optical bare $101.95M vs
"One stop 1/2/3" leaves summing to $40.96M). These represent the
issuer's holding-company equity that the filer didn't tag at leaf
level. The generic extractor drops them because cost=0, leaving GBDC
~1% under-extracted vs the canonical XBRL portfolio total. The trade-off
is intentional: keeping them risks double-counting in filers that don't
have this pattern.
"""
from __future__ import annotations
from ._base import Bdc
from . import register


@register
class Gbdc(Bdc):
    ticker = "GBDC"
    canonical_fv_m = 8317.2
    canonical_period = "2026-03-31"
    keep_partial_rollup_excess = True
