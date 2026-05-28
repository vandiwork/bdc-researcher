"""BXSL — Blackstone Secured Lending Fund (CIK 0001736035).

Conventional XBRL with standard "Issuer, Tranche" labels. Generic logic
brings it to within 2% of the dashboard.
"""
from __future__ import annotations
from ._base import Bdc
from . import register


@register
class Bxsl(Bdc):
    ticker = "BXSL"
    canonical_fv_m = 14207.0
    canonical_period = "2025-12-31"
