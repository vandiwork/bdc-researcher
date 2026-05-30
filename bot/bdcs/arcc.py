"""ARCC — Ares Capital Corporation (CIK 0001287750).

Conventional XBRL: typed `InvestmentIdentifierAxis` with comma-separated
"Issuer Name, Tranche Description" labels. Sub-SOIs from SDLP and Ivy Hill
appear as issuer-level roll-ups that get filtered by the generic prefix
detector. No filer-specific quirks needed.
"""
from __future__ import annotations
from ._base import Bdc
from . import register


@register
class Arcc(Bdc):
    ticker = "ARCC"
    canonical_fv_m = 29499.3
    canonical_period = "2026-03-31"
