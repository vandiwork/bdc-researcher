"""BXSL — Blackstone Secured Lending Fund (CIK 0001736035).

BXSL labels every position with an "| Non-Affiliated Issuer" affiliation
suffix on the InvestmentIdentifierAxis (e.g.
"Aevex Holdings, LLC 1 | Non-Affiliated Issuer"). Strip it so the entity
displays cleanly. Real affiliation belongs in the dedicated affil column.
"""
from __future__ import annotations
import re as _re
from ._base import Bdc
from . import register


# Trailing "| <Affiliation Type>" suffix that BXSL appends to every label.
# Matches "Non-Affiliated Issuer", "Affiliated Issuer", "Controlled Issuer".
_BXSL_AFFIL_SUFFIX = _re.compile(
    r"\s*\|\s*(?:Non[- ]Affiliated|Affiliated|Controlled)\s+Issuer\s*$",
    _re.I,
)
# Trailing tranche-number suffix on entity (e.g. "Aevex Holdings, LLC 1").
_BXSL_TRANCHE_NUM = _re.compile(r"\s+\d+\s*$")


@register
class Bxsl(Bdc):
    ticker = "BXSL"
    canonical_fv_m = 13942.1
    canonical_period = "2026-03-31"

    def parse_identifier(self, ident: str) -> dict:
        # Identifier shape: "<Entity Name>[, Inc./LLC/Corp/LP] <n> | <Affiliation>"
        # Examples:
        #   "Aevex Holdings, LLC 1 | Non-Affiliated Issuer"
        #   "Corfin Holdings, Inc. 2 | Non-Affiliated Issuer"
        # The integer suffix (1/2/…) is the tranche index — keep entity intact
        # including the corporate suffix; HTML enrichment supplies sector/type.
        head = _BXSL_AFFIL_SUFFIX.sub("", ident).strip()
        entity = _BXSL_TRANCHE_NUM.sub("", head).strip()
        return {"entity": entity} if entity else {}
