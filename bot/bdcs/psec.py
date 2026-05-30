"""PSEC — Prospect Capital Corp (CIK 0001287032).

PSEC tags every multi-tranche issuer TWICE:
  - one row per leaf tranche (identifier = "<Issuer> | <Sector> | <Type>")
  - plus one ISSUER-LEVEL ROLLUP row (identifier = just "<Issuer>")
The rollup's FV equals the sum of the leaves, so including it double-
counts ~$2.3B (~36% of the portfolio).

Distinguishing feature: rollup identifiers have NO " | " separator.
We drop them via `should_drop_identifier`.
"""
from __future__ import annotations
import re as _re
from ._base import Bdc
from . import register


@register
class Psec(Bdc):
    ticker = "PSEC"
    canonical_fv_m = 6302.5
    canonical_period = "2026-03-31"   # Q3 FY26 (PSEC fiscal year ends 6/30)

    drop_identifier_patterns = (
        # Original alias whose FV equals two specific Spartan tranches
        _re.compile(r"^CP Energy - "),
        # Issuer-level rollups: identifier is just "<Issuer Name>" with
        # no " | " section. Anchored ^ + $ on full string + no "|".
        _re.compile(r"^[^|]+$"),
    )

    def post_filter(self, positions: list) -> list:
        # PSEC also tags some positions twice: a canonical row with
        # sector + cost (e.g. "Aventiv Technologies, LLC, Diversified
        # Telecommunication Services, ...") and a short alias with no
        # sector and no cost. The alias has the same FV. Drop cost=0
        # rows whose FV matches any other row's FV.
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
