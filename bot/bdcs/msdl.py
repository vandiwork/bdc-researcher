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

_MSDL_AFFIL_PFX = re.compile(
    r"^(?:Debt|Equity|Warrant)?\s*Investments[-\s]+(?:non[-\s]+)?"
    r"(?:controlled|affiliated)"
    r"(?:[/-](?:non[-\s]+)?(?:controlled|affiliated))*\s+", re.I)
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
)


@register
class Msdl(Bdc):
    ticker = "MSDL"
    canonical_fv_m = 3668.9
    canonical_period = "2026-03-31"
    reconcile_to_reported = True
    column_aliases = {"Investments": "company"}
    value_scale_m = 0.001

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
        return kept

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
