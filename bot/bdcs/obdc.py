"""OBDC — Blue Owl Capital Corporation (CIK 0001655888).

Main-portfolio identifiers use the three-pipe format:
    "<Issuer> | <Tranche Description> | <Affiliation>"

OBDC also tags ~24 "sub-SOI rollup" rows that have no pipe separators and
no cost basis (cost=0 / null, fv>0). These represent positions in the
joint-venture vehicles (LSI Financing 1 DAC, Wingspire, Amergin, etc.)
which the dashboard reports via OBDC's equity stake in the JV, not by
look-through. We drop rows lacking a pipe AND with cost missing/zero.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


_TYPE_FROM_TRANCHE = [
    ("First Lien",          re.compile(r"first lien", re.I)),
    ("Second Lien",         re.compile(r"second lien", re.I)),
    ("Senior Subordinated", re.compile(r"senior subordinated", re.I)),
    ("Subordinated",        re.compile(r"\bsubordinated\b", re.I)),
    ("Preferred Equity",    re.compile(r"preferred (?:equity|stock|unit|interest)", re.I)),
    ("Warrant",             re.compile(r"\bwarrant", re.I)),
    ("Common Equity",       re.compile(r"common (?:equity|stock|unit|interest)", re.I)),
    ("LP Interest",         re.compile(r"\b(?:lp|limited partner)\s+(?:interest|unit)", re.I)),
    ("LLC Interest",        re.compile(r"\b(?:llc|member(?:ship)?)\s+interest", re.I)),
    ("Equity",              re.compile(r"\b(?:equity|share|unit|interest)\b", re.I)),
]

# Field separator is a pipe, but some rows render it without surrounding
# spaces ("Inc.| First lien") or with the pipe mis-encoded as a capital "I"
# ("Flexera Software LLC I First lien ..."). Treat a bare " I " as a separator
# ONLY when it precedes a tranche/type keyword so real names like "Fund I" or
# "Class I" are left intact.
_OBDC_SEP = re.compile(
    r"\s*\|\s*"
    r"|\s+I\s+(?=First|Second|Senior|Subordinated|Unsecured|Preferred|Common|"
    r"LP\b|LLC\b|Warrant|Delayed|Term|Revolv|Mezzanine|Equity)",
    re.I,
)


@register
class Obdc(Bdc):
    ticker = "OBDC"
    canonical_fv_m = 15344.2
    canonical_period = "2026-03-31"

    def post_filter(self, positions: list) -> list:
        # Drop sub-SOI rollup rows: no separator, cost missing/zero.
        kept = []
        for p in positions:
            no_pipe = len(_OBDC_SEP.split(p.identifier)) < 2
            cost_missing = p.cost is None or p.cost == 0
            if no_pipe and cost_missing:
                continue
            kept.append(p)
        return kept

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}
        parts = [p.strip() for p in _OBDC_SEP.split(ident)]
        if len(parts) >= 2:
            out["entity"] = parts[0]
            tranche = parts[1]
            for tname, rx in _TYPE_FROM_TRANCHE:
                if rx.search(tranche):
                    out["type"] = tname
                    break
        return out
