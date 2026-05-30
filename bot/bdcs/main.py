"""MAIN — Main Street Capital Corp (CIK 0001396440).

Identifier format: `<Issuer> | <Tranche Description> [<n>][<.n>]`

MAIN tags each equity tranche twice — once canonically, once as a `.X`
suffix alias with cost=0. Both need to share the same parsed entity for
the generic dedup to merge them, so we split on " | " first and use the
pre-pipe issuer as `entity`. We also map MAIN's vocabulary
("Secured Debt", "Member Units", "Preferred Member Units") to the
standard `type` taxonomy.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


_TYPE_FROM_TRANCHE = [
    ("Secured Debt",         re.compile(r"^Secured Debt\b", re.I)),
    ("First Lien",           re.compile(r"first[- ]lien", re.I)),
    ("Subordinated",         re.compile(r"subordinated", re.I)),
    ("Preferred Equity",     re.compile(r"^Preferred (?:Member |Equity|Stock|Unit|Share)", re.I)),
    ("Warrant",              re.compile(r"^Warrant", re.I)),
    ("Common Equity",        re.compile(r"^Common (?:Stock|Equity|Unit)", re.I)),
    ("Equity",               re.compile(r"^(?:Member Units?|LLC Units?|LP Units?|Common Units?|Class [A-Z])", re.I)),
]


@register
class Main(Bdc):
    ticker = "MAIN"
    canonical_fv_m = 5674.8
    canonical_period = "2026-03-31"

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}
        if " | " in ident:
            head, _, tail = ident.partition(" | ")
            out["entity"] = head.strip()
            tail = tail.strip()
            for tname, rx in _TYPE_FROM_TRANCHE:
                if rx.search(tail):
                    out["type"] = tname
                    break
        return out

    def post_filter(self, positions: list) -> list:
        # MAIN tags many positions twice with different entity names:
        # a canonical row under one LMM/structure name with cost+FV, and
        # an alias row under a different "holding LLC" or "L.P." label
        # with cost=0 but the same FV. Catches Johnson Downie Opco, HPEP 3,
        # 423 HAR, 2717 MH, Freeport Financial SBIC, etc.
        # Drop cost=0 rows whose FV matches any cost-bearing row's FV.
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
