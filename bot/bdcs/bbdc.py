"""BBDC — Barings BDC, Inc. (CIK 0001379785).

Conventional XBRL with pipe-delimited identifier labels. Generic dedup
catches the alias pattern; sub-entity filter handles any consolidated
sub-SOIs.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


@register
class Bbdc(Bdc):
    ticker = "BBDC"
    canonical_fv_m = 2399.0
    canonical_period = "2025-12-31"

    # BBDC tags some revolver / second-lien loans with a redundant
    # ", Funded" or " | Funded" suffix that aliases the canonical row.
    drop_identifier_patterns = (
        re.compile(r"[,|]\s*Funded\s*$", re.I),
    )

    def post_filter(self, positions: list) -> list:
        # BBDC has ~11 alias rows where the entity name has a typo
        # variation (e.g. "Biolam" vs "Biolam Group", "Security Holdings B.V"
        # vs "Security Holdings B.V.") so the generic entity-keyed dedup
        # misses them. Catch the residual: a row with cost=0/null AND FV
        # equal to some other row's FV — even across different entities —
        # is an alias. Skip warrants (Type=Warrant) where cost=0 is legit.
        from collections import Counter
        fv_count: Counter[int] = Counter()
        for p in positions:
            if p.fv:
                fv_count[round(p.fv)] += 1
        kept = []
        for p in positions:
            cost_zero = (p.cost is None) or (p.cost == 0)
            fv_has_sibling = p.fv and fv_count.get(round(p.fv), 0) > 1
            if (cost_zero and fv_has_sibling
                    and p.type not in ("Warrant",)):
                continue
            kept.append(p)
        return kept
