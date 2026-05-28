"""FSK — FS KKR Capital Corp (CIK 0001422183).

FSK consolidates several JV vehicles (notably the Credit Opportunities
Partners JV) whose underlying portfolios are disclosed in the 10-K as
separate SOI tables. Many of these positions appear with no cost basis
(cost=0, fv>0) or with sector-only suffixes.

Identifier format:
    "<Issuer> | <Sector> [<n>]"     — main portfolio (n is tranche idx)
    "<Issuer>, <Tranche descriptor>" — equity/warrant aliases
    "<Issuer>"                       — sub-SOI alias (drop)

Filter: drop standalone aliases (no " | " separator AND no comma) that
have FV but no cost — these are JV sub-SOI placeholders.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


@register
class Fsk(Bdc):
    ticker = "FSK"
    canonical_fv_m = 14404.0
    canonical_period = "2025-12-31"

    def post_filter(self, positions: list) -> list:
        # Pass 1: drop sub-SOI rollups (no pipe, no comma, no cost).
        out = []
        for p in positions:
            ident = p.identifier
            no_pipe = " | " not in ident
            no_comma = "," not in ident
            cost_missing = p.cost is None or p.cost == 0
            if no_pipe and no_comma and cost_missing:
                continue
            out.append(p)

        # Pass 2: drop cost=0 alias rows whose FV matches a cost-bearing
        # row for the same parsed entity (catches plain alias pattern).
        from collections import defaultdict
        by_ent_fv: dict[str, set[int]] = defaultdict(set)
        all_cost_fvs: set[int] = set()
        for p in out:
            if p.cost and p.cost > 0 and p.fv:
                key = round(p.fv)
                by_ent_fv[p.entity].add(key)
                all_cost_fvs.add(key)

        # Pass 3: FSK also has cross-entity aliases where the entity name
        # differs cosmetically — e.g. "Roemanu LLC" vs "Roemanu LLC (FKA
        # Toorak Capital Partners LLC)", or typo "gHM Dunn Co Inc" vs
        # "HM Dunn Co Inc". Drop cost=0 rows with FV >= $5M when ANY
        # other row in the filing has the same FV.
        final = []
        for p in out:
            if (p.cost is None or p.cost == 0) and p.fv:
                key = round(p.fv)
                if key in by_ent_fv.get(p.entity, set()):
                    continue
                if p.fv >= 5_000_000 and key in all_cost_fvs:
                    continue
            final.append(p)
        return final

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
