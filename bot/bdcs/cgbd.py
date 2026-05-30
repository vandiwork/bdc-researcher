"""CGBD — Carlyle Secured Lending, Inc. (CIK 0001544206).

The 10-K includes a sub-SOI for Middle Market Credit Fund LLC (a JV).
Those rows use an extension taxonomy without the standard
`InvestmentCompanyNonconsolidatedSubsidiaryAxis` dimension, so we filter
them by their identifier prefix `"Credit Fund |"`.

There are also a handful of redundant standalone labels (e.g.
`"Middle Market Credit Fund, LLC, Subordinated Loan and Member's Interest"`)
that duplicate canonical pipe-delimited rows — these get caught by the
generic FV-match dedupe, but we also add them as exact-drop labels for
robustness.

Identifier format for main portfolio:
    "Investment | <Affiliation> | <Type> | <Issuer> | <Sector>"
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register

# Canonical form: "Investment | <Affil> | <Type> | <Issuer> | <Sector>"
_PFX_FULL = re.compile(
    r"^Investment\s*\|\s*(?P<affil>[^|]+?)\s*\|\s*(?P<type>[^|]+?)\s*\|\s*"
    r"(?P<issuer>.+?)\s*\|\s*(?P<sector>.+?)\s*$")
# Alias form (no sector pipe, trailing tranche index):
#   "Investment | <Affil> | <Type>, | <Issuer> <N>"
_PFX_ALIAS = re.compile(
    r"^Investment\s*\|\s*(?P<affil>[^|]+?)\s*\|\s*(?P<type>[^|]+?),?\s*\|\s*"
    r"(?P<issuer>.+?)\s*$")
# Trailing " <digit>" (alias tranche index) — strip from issuer
_TRAILING_NUM = re.compile(r"\s+\d+\s*$")

_TYPE_MAP = {
    "First Lien Debt": "First Lien",
    "Second Lien Debt": "Second Lien",
    "Subordinated Debt": "Subordinated",
    "Equity Investments": "Equity",
    "Investment Funds": "Investment Funds",
}


@register
class Cgbd(Bdc):
    ticker = "CGBD"
    canonical_fv_m = 2277.1
    canonical_period = "2026-03-31"

    drop_identifier_prefixes = ("Credit Fund ",)
    drop_identifier_exact = frozenset({
        # Standalone aliases of pipe-delimited rows
        "Middle Market Credit Fund, LLC, Subordinated Loan and Member’s Interest",
        "Middle Market Credit Fund, LLC, Mezzanine Loan",
    })

    # CGBD has a labelling error pattern where equity positions in
    # affiliated issuers get a duplicate alias row with the issuer name
    # suffixed " (Equity)" and the XBRL type-pipe stuck at "First Lien
    # Debt,". The canonical row exists elsewhere in the "Equity Investments"
    # type pipe with the same FV. Drop the "(Equity)" alias.
    drop_identifier_patterns = (
        re.compile(r"\(Equity\)\s*$"),
    )

    def parse_identifier(self, ident: str) -> dict:
        m = _PFX_FULL.match(ident)
        sector = None
        if m:
            sector = m.group("sector").strip()
        else:
            m = _PFX_ALIAS.match(ident)
            if not m:
                return {}
        type_raw = m.group("type").strip().rstrip(",").rstrip()
        issuer = m.group("issuer").strip().rstrip(",").rstrip()
        # Strip alias-marker " 1" / " 2" suffix so canonical and alias share
        # the same parsed entity and the generic FV-dedupe can merge them.
        issuer = _TRAILING_NUM.sub("", issuer).strip()
        out: dict = {
            "entity": issuer,
            "type": _TYPE_MAP.get(type_raw, type_raw),
        }
        if sector:
            out["sector"] = sector
        return out
