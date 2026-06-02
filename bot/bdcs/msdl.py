"""MSDL — Morgan Stanley Direct Lending Fund (CIK 0001782524).

MSDL's XBRL identifier embeds affiliation + section + sector before the
issuer:
  "Investments-non-controlled/non-affiliated Debt Investments Food
   Products Familia Intermediate Holdings I Corp. (Teasdale Latin Foods)"

Strategy: strip the affiliation prefix, then "Debt Investments" / "Equity
Investments", then known sectors.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register

# NB: MSDL separates "Investments" from the affiliation word with an EM-DASH
# (U+2014), not a hyphen — e.g. "Investments—non-controlled/non-affiliated".
# The character class must include the em/en-dash or the whole prefix leaks
# into the issuer name. (– en-dash, — em-dash)
_DASH = r"\-–—"
_MSDL_AFFIL_PFX = re.compile(
    r"^(?:Debt|Equity|Warrant)?\s*Investments[" + _DASH + r"\s]+(?:non[" + _DASH + r"\s]+)?"
    r"(?:controlled|affiliated)"
    r"(?:[/" + _DASH + r"](?:non[" + _DASH + r"\s]+)?(?:controlled|affiliated))*\s+", re.I)
_MSDL_SECTION_PFX = re.compile(
    r"^(Debt|Equity|Warrant) Investments\s+", re.I)


_MSDL_SPREAD_RX = re.compile(
    r"\bReference Rate and Spread\s+([SEPL])\s*\+\s*([\d.]+)\s*%", re.I)
_MSDL_RATE_RX = re.compile(r"\bInterest Rate\s+([\d.]+)\s*%")
_MSDL_MAT_RX = re.compile(r"\bMaturity Date\s+(\d{1,2}/\d{1,2}/\d{2,4})")

# MSDL sectors observed (used to peel sector prefix off the issuer)
_MSDL_SECTORS = (
    "Aerospace & Defense", "Air Freight & Logistics", "Automobiles",
    "Banking", "Banks", "Beverages", "Biotechnology",
    "Building Products", "Capital Markets", "Chemicals",
    "Commercial Services & Supplies", "Communications Equipment",
    "Construction & Engineering", "Construction Materials",
    "Consumer Finance", "Containers & Packaging",
    "Distributors", "Diversified Consumer Services",
    "Diversified Financial Services", "Diversified Telecommunication Services",
    "Electric Utilities", "Electrical Equipment",
    "Electronic Equipment, Instruments & Components",
    "Energy Equipment & Services", "Entertainment",
    "Food & Staples Retailing", "Food Products",
    "Gas Utilities", "Health Care Equipment & Supplies",
    "Health Care Providers & Services", "Health Care Technology",
    "Hotels, Restaurants & Leisure", "Household Durables",
    "Household Products", "Independent Power and Renewable Electricity Producers",
    "Industrial Conglomerates", "Insurance",
    "Insurance Services", "Interactive Media & Services",
    "Internet & Direct Marketing Retail", "Internet Software and Services",
    "IT Services", "Leisure Products", "Life Sciences Tools & Services",
    "Machinery", "Marine", "Media", "Metals & Mining",
    "Multi-Utilities", "Multiline Retail", "Office Services & Supplies",
    "Oil, Gas & Consumable Fuels", "Paper & Forest Products",
    "Personal Products", "Pharmaceuticals",
    "Professional Services", "Real Estate Management & Development",
    "Real Estate Mgmt. & Development", "Road & Rail",
    "Semiconductors & Semiconductor Equipment",
    "Software", "Specialty Retail", "Tax Services",
    "Technology Hardware, Storage & Peripherals",
    "Textiles, Apparel & Luxury Goods", "Thrifts & Mortgage Finance",
    "Tobacco", "Trading Companies & Distributors", "Transportation Infrastructure",
    "Water Utilities", "Wireless Telecommunication Services",
    # GICS-2023 industry renames + section labels seen in MSDL filings.
    "Automobile Components", "Consumer Staples Distribution & Retail",
    "Financial Services", "Ground Transportation",
    "Passenger Airlines", "Health Care REITs",
    "Investments in Joint Ventures",
)


@register
class Msdl(Bdc):
    ticker = "MSDL"
    canonical_fv_m = 3668.9
    canonical_period = "2026-03-31"
    column_aliases = {"Investments": "company"}
    value_scale_m = 0.001
    # MSDL consolidates a wholly-owned financing subsidiary ("Capstone
    # Lending") and ALSO prints that subsidiary's standalone "Consolidated
    # Schedule of Investments" further down the 10-Q (after the prior-period
    # comparative schedule). Those rows duplicate holdings already in the
    # main consolidated SOI and need to be dropped by document position.
    needs_doc_positions = True

    # MSDL tags JV / controlled equity stakes twice — once with the long-form
    # "Investments controlled/affiliated Equity Investments Investments in
    # Joint Ventures <Entity>, …" identifier (cost > 0) and once with a bare
    # "<Entity>" alias (cost = 0). Drop the bare aliases when a long-form
    # row with the same FV is present.
    def post_filter(self, positions: list) -> list:
        all_cost_fvs: set[int] = set()
        for p in positions:
            if p.cost and p.cost > 0 and p.fv:
                all_cost_fvs.add(round(p.fv))
        kept = []
        for p in positions:
            ident = p.identifier or ""
            is_bare = not ident.startswith("Investments")
            cost_missing = p.cost is None or p.cost == 0
            if is_bare and cost_missing and p.fv and round(p.fv) in all_cost_fvs:
                continue
            kept.append(p)
        return self._drop_subsidiary_subschedule(kept)

    def _drop_subsidiary_subschedule(self, positions: list) -> list:
        """Drop the consolidated-subsidiary standalone Schedule of Investments
        that MSDL prints after the comparative-period schedule. Its rows
        re-list holdings already counted in the main consolidated SOI
        (~$0.28B), so the straight sum over-states the portfolio by that much.

        The sub-schedule is a contiguous block at the end of the document, so
        among current-period positions (sorted by byte offset in the primary
        doc) it sits after the single largest doc-position gap — the gap left
        by the comparative-period schedule, whose facts are a different period
        and therefore absent here. We only drop it when doing so reconciles
        the portfolio to the filer's reported total (a guard so a future
        filing with a different structure is never silently truncated)."""
        tgt = self.canonical_fv_m
        withpos = [p for p in positions if p.doc_pos is not None and p.fv]
        if not tgt or len(withpos) < 50:
            return positions
        ordered = sorted(withpos, key=lambda p: p.doc_pos)
        gi, _gap = max(
            ((i, ordered[i + 1].doc_pos - ordered[i].doc_pos)
             for i in range(len(ordered) - 1)),
            key=lambda t: t[1])
        tail = ordered[gi + 1:]
        if not tail:
            return positions
        full = sum((p.fv or 0) for p in positions) / 1e6
        head = full - sum((p.fv or 0) for p in tail) / 1e6
        if abs(head - tgt) / tgt < 0.015 and abs(full - tgt) / tgt > 0.03:
            drop = {id(p) for p in tail}
            return [p for p in positions if id(p) not in drop]
        return positions

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}

        # Extract trailing field markers
        m = _MSDL_SPREAD_RX.search(ident)
        if m:
            out["base_rate"] = {"S": "SOFR", "E": "EURIBOR",
                                "P": "Prime", "L": "LIBOR"}.get(
                m.group(1).upper(), m.group(1).upper())
            out["spread"] = float(m.group(2))
        m = _MSDL_RATE_RX.search(ident)
        if m:
            out["rate"] = float(m.group(1))
        m = _MSDL_MAT_RX.search(ident)
        if m:
            mo, dy, yr = m.group(1).split("/")
            yr_full = int(yr) if len(yr) == 4 else (
                2000 + int(yr) if int(yr) <= 50 else 1900 + int(yr))
            out["maturity"] = f"{yr_full}-{int(mo):02d}-{int(dy):02d}"

        # Parse out the issuer
        s = ident
        # Some MSDL identifiers double-prepend the affiliation/section
        # prefix; loop until no more matches.
        for _ in range(4):
            stripped = False
            m = _MSDL_AFFIL_PFX.match(s)
            if m:
                s = s[m.end():]
                stripped = True
            m = _MSDL_SECTION_PFX.match(s)
            if m:
                s = s[m.end():]
                stripped = True
            if not stripped:
                break
        # Strip sector prefix
        for sect in sorted(_MSDL_SECTORS, key=len, reverse=True):
            if s.startswith(sect + " "):
                out["sector"] = sect
                s = s[len(sect) + 1:]
                break
        # Trim trailing " Investment <Type>" / " Reference Rate ..." etc.
        for kw in (" Investment First", " Investment Second",
                   " Investment Senior", " Investment Subordinated",
                   " Investment Preferred", " Investment Common",
                   " Investment Limited", " Investment Equity",
                   " Investment Warrants", " Investment LLC",
                   " Investment LP", " Investment Loan",
                   " Investment Membership", " Investment Term",
                   " Reference Rate", " Interest Rate", " Maturity Date"):
            idx = s.find(kw)
            if idx > 0:
                s = s[:idx].rstrip()
                break
        if s and s != ident:
            out["entity"] = s
        return out
