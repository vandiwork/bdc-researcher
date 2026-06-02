"""BCRED — Blackstone Private Credit Fund (CIK 0001803498).

Non-listed perpetual BDC, same filer family as BXSL. Two quirks:

1. Identifiers carry an affiliation suffix "<Entity> [<n>] | <Affiliation>"
   exactly like BXSL — strip it for a clean entity name.

2. BCRED holds two consolidated-for-disclosure joint ventures, the
   Emerald JV and Verdelite JV. The 10-Q XBRL tags BOTH:
     - the JV equity stake  ("BCRED Emerald JV LP - LP Interest", ~$1.5B)
     - every look-through holding inside the JV
       ("<Issuer> ... | Emerald JV LP", "... | Verdelite JV LP")
   The consolidated `InvestmentOwnedAtFairValue` ($80.5B) counts the JV
   at the equity stake only, NOT the gross look-through (~$7.8B). So we
   drop every look-through row (suffix "| <Name> JV LP") and keep the
   bare LP-Interest rows. This removes a ~$7.8B (~10%) double-count.
"""
from __future__ import annotations
import re as _re
from ._base import Bdc
from . import register


# Affiliation suffix appended to every BCRED identifier.
_BCRED_AFFIL_SUFFIX = _re.compile(
    r"\s*\|\s*(?:Non[- ]Controlled |Controlled |Non[- ])?"
    r"(?:Affiliated|Non-Affiliated)?\s*(?:Issuer|User)\s*$",
    _re.I,
)
_BCRED_TRANCHE_NUM = _re.compile(r"\s+\d+\s*$")
# Look-through rows live inside a JV: identifier ends "| <Name> JV LP".
_BCRED_JV_LOOKTHROUGH = _re.compile(r"\|\s*\w[\w\s]*\bJV LP\s*$", _re.I)


@register
class Bcred(Bdc):
    ticker = "BCRED"
    canonical_fv_m = 80469.4
    canonical_period = "2026-03-31"

    drop_identifier_patterns = (
        # Drop JV look-through holdings; keep the bare LP-Interest stake
        # ("BCRED Emerald JV LP - LP Interest" has no leading "| ").
        _BCRED_JV_LOOKTHROUGH,
    )

    def parse_identifier(self, ident: str) -> dict:
        head = _BCRED_AFFIL_SUFFIX.sub("", ident).strip()
        entity = _BCRED_TRANCHE_NUM.sub("", head).strip()
        return {"entity": entity} if entity else {}
