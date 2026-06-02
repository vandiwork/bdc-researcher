"""FSK — FS KKR Capital Corp (CIK 0001422183).

FSK tags every real Schedule-of-Investments position WITH a sector pipe:
    "<Issuer>, <Tranche> | <Sector> [<n>]"
The SAME positions are re-tagged WITHOUT the pipe ("<Issuer>, <Tranche>")
in supplemental fair-value-hierarchy and affiliated-rollforward tables.
Those no-pipe rows are duplicates — the with-pipe set is the complete SOI
and ties exactly to FSK's own section subtotals ($13.6B gross). So we keep
with-pipe rows and drop the rest.

NOTE: FSK does NOT disclose the individual holdings of its Credit
Opportunities Partners JV — only a one-paragraph summary note (total debt
$4.3B, 154 companies). There is therefore NO JV look-through to remove; an
earlier handler wrongly deleted FSK's real equity (athenahealth, JW
Aluminum, …) on that mistaken premise. FSK prints positions GROSS and nets
~$1.3B of unfunded commitments on separate negative InvestmentTypeAxis
lines; that netting is handled generically in extract_bdc_soi.parse_facts.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


@register
class Fsk(Bdc):
    ticker = "FSK"
    canonical_fv_m = 12269.4
    canonical_period = "2026-03-31"

    def post_filter(self, positions: list) -> list:
        # Keep the Schedule-of-Investments rows (sector pipe present); drop
        # the no-pipe duplicate copies that FSK re-lists in supplemental
        # fair-value-hierarchy / affiliated-rollforward tables. The with-pipe
        # set is the complete SOI and ties to FSK's own section subtotals.
        return [p for p in positions if " | " in (p.identifier or "")]

    def parse_identifier(self, ident: str) -> dict:
        # FSK label patterns:
        #   "<Issuer> | <Sector> [<n>]"       — debt main portfolio
        #   "<Issuer>, <Tranche> | <Sector>"  — equity / warrant
        #   "<Issuer>, <Tranche>"             — equity alias (no pipe)
        # Sector extraction comes from the pipe; entity should be the
        # comma-prefix when present so that alias rows merge with their
        # canonical sibling.
        out: dict = {}
        head = ident
        if " | " in ident:
            head, _, rest = ident.partition(" | ")
            m = re.match(r"^(.*?)\s+(\d+)\s*$", rest)
            out["sector"] = m.group(1).strip() if m else rest.strip()
        # Pull issuer from the pre-comma part of `head` if a tranche desc
        # follows. Avoids the alias issue where pipe form keeps the tranche.
        if "," in head:
            issuer_part = head.split(",", 1)[0].strip()
            out["entity"] = issuer_part
        else:
            out["entity"] = head.strip()
        return out
