"""PSEC — Prospect Capital Corp (CIK 0001287032).

Conventional XBRL. Generic logic matches dashboard within 2.2%.
"""
from __future__ import annotations
from ._base import Bdc
from . import register


import re as _re


@register
class Psec(Bdc):
    ticker = "PSEC"
    canonical_fv_m = 6674.0
    canonical_period = "2025-06-30"   # PSEC fiscal year ends June 30

    # PSEC has one partial-rollup alias whose FV equals the sum of two
    # specific child tranches: "CP Energy - Spartan Energy Services, Inc."
    # (the " - " in the entity name is the alias marker — no other PSEC
    # canonical label uses that pattern).
    drop_identifier_patterns = (
        _re.compile(r"^CP Energy - "),
    )

    def post_filter(self, positions: list) -> list:
        # PSEC tags some positions twice: a canonical row with sector +
        # cost (e.g. "Aventiv Technologies, LLC, Diversified
        # Telecommunication Services, ...") and a short alias with no
        # sector and no cost. The alias has the same FV. Drop cost=0
        # rows whose FV matches any other row's FV (no min threshold —
        # catches Aventiv's $0.72M alias).
        all_cost_fvs = set()
        for p in positions:
            if p.cost and p.cost > 0 and p.fv:
                all_cost_fvs.add(round(p.fv))
        kept = []
        for p in positions:
            if (p.cost is None or p.cost == 0) and p.fv and p.fv > 0:
                if round(p.fv) in all_cost_fvs:
                    continue
            kept.append(p)
        return kept
