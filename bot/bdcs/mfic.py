"""MFIC — MidCap Financial Investment Corp (CIK 0001278752).

Identifier format embeds sector first:
    "<Sector>, <Issuer> <Type> - <Subtype> SOFR+<Spread>, <Floor>% Floor
     Maturity <Maturity>"

e.g.:
    "Aerospace & Defense, Beaufort Eagle U.S. Purchaser, Inc. First Lien
     Secured Debt - Term Loan SOFR+500, 0.75% Floor Maturity ..."
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register

_TYPE_PATTERNS = [
    ("First Lien",       re.compile(r"First Lien", re.I)),
    ("Second Lien",      re.compile(r"Second Lien", re.I)),
    ("Subordinated",     re.compile(r"Subordinated", re.I)),
    ("Preferred Equity", re.compile(r"Preferred Equity", re.I)),
    ("Common Equity",    re.compile(r"Common Equity", re.I)),
    ("Warrant",          re.compile(r"\bWarrant", re.I)),
    ("Equity",           re.compile(r"\bEquity\b", re.I)),
]
_SPREAD_RX = re.compile(r"SOFR\s*\+\s*(\d+)\b", re.I)
_RATE_RX = re.compile(r"Interest Rate\s+([0-9]+\.[0-9]+)%", re.I)

_MFIC_SECTORS = (
    "Aerospace & Defense", "Air Freight & Logistics",
    "Automobile Components", "Automobiles", "Banks",
    "Beverages", "Biotechnology", "Building Products",
    "Capital Markets", "Chemicals",
    "Commercial Services & Supplies", "Communications Equipment",
    "Construction & Engineering", "Construction Materials",
    "Consumer Finance", "Consumer Staples Distribution",
    "Containers & Packaging", "Distributors",
    "Diversified Consumer Services", "Diversified Financial Services",
    "Diversified Telecommunication Services",
    "Electric Utilities", "Electrical Equipment",
    "Electronic Equipment, Instruments & Components",
    "Energy Equipment & Services", "Entertainment",
    "Financial Services", "Food Products",
    "Health Care Equipment & Supplies",
    "Health Care Providers & Services", "Health Care Technology",
    "Hotels, Restaurants & Leisure", "Household Durables",
    "Household Products", "IT Services", "Industrial Conglomerates",
    "Insurance", "Interactive Media & Services",
    "Internet & Direct Marketing Retail",
    "Leisure Products", "Life Sciences Tools & Services",
    "Machinery", "Media", "Metals & Mining", "Multi-Utilities",
    "Office Services & Supplies", "Oil, Gas & Consumable Fuels",
    "Personal Products", "Pharmaceuticals",
    "Professional Services", "Real Estate Management & Development",
    "Semiconductors & Semiconductor Equipment",
    "Software", "Specialty Retail",
    "Technology Hardware, Storage & Peripherals",
    "Textiles, Apparel & Luxury Goods",
    "Trading Companies & Distributors",
    "Transportation Infrastructure",
    "Wireless Telecommunication Services",
    "Independent Power and Renewable Electricity Producers",
)


@register
class Mfic(Bdc):
    ticker = "MFIC"
    canonical_fv_m = 3168.0
    canonical_period = "2025-12-31"

    # MFIC reports redundant alias rows for each consolidated- or
    # affiliated-investment position with prefixes "Controlled Investments "
    # and "Affiliated Investments " (the canonical row uses the
    # sector-led format).
    drop_identifier_prefixes = (
        "Controlled Investments ",
        "Affiliated Investments ",
    )

    def parse_identifier(self, ident: str) -> dict:
        # MFIC format mixes two shapes:
        #   "<Sector> <Issuer> <Type> ..."     (sectors without commas)
        #   "<Sector>, <Issuer>, <Type> ..."   (sectors that contain commas
        #                                       use comma as outer sep)
        # Strategy: peel a known sector from the start; if the sector text
        # is followed by ", " treat as comma-form, else as space-form. Then
        # find the type marker to delimit issuer end.
        out: dict = {}
        s = ident
        sector_found = ""
        for sect in sorted(_MFIC_SECTORS, key=len, reverse=True):
            if s.startswith(sect + ", "):
                sector_found = sect
                s = s[len(sect) + 2:]
                break
            if s.startswith(sect + " "):
                sector_found = sect
                s = s[len(sect) + 1:]
                break
        if sector_found:
            out["sector"] = sector_found

        # Now s starts with the issuer. Find where the type marker begins.
        type_idx = -1
        for tname, rx in _TYPE_PATTERNS:
            m = rx.search(s)
            if m:
                out["type"] = tname
                type_idx = m.start()
                break
        if type_idx >= 0:
            head = s[:type_idx].strip(" ,.")
        else:
            head = s.strip(" ,.")

        # The issuer may itself contain ", <Subsidiary>" — keep the first
        # comma-bounded segment as the entity (the parent name). If the
        # head is short, keep it whole.
        if "," in head:
            parts = [p.strip() for p in head.split(",")]
            # Drop trailing parts that look like duplicate subsidiary names
            # (heuristic: same as previous after stripping ' LLC'/'Inc.')
            out["entity"] = parts[0]
        else:
            out["entity"] = head

        m = _SPREAD_RX.search(ident)
        if m:
            out["spread"] = int(m.group(1)) / 100.0
            out["base_rate"] = "SOFR"
        return out
