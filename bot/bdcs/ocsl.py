"""OCSL — Oaktree Specialty Lending Corp (CIK 0001414932).

OCSL consolidates the Oaktree Strategic Credit Fund (OSCF) JV. The 10-K
includes the JV's full SOI tagged with the standard
`InvestmentCompanyNonconsolidatedSubsidiaryAxis` dimension — the base-class
filter excludes them. Net result matches the dashboard within 0.3%.

OCSL identifier shape:
    "<Issuer>, <Sector>, <Type>"
e.g. "OCSI Glick JV LLC, Multi-Sector Holdings, Subordinated Debt"
     "Latham Pool Products, Inc., Distributors, Senior Secured First Lien"

Corporate suffixes (Inc., LLC, L.P., etc.) inside the issuer name use
commas too, so we walk segments and treat known sectors / suffixes
appropriately.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


_CORP_SUFFIX_RX = re.compile(
    r"^(?:Inc|LLC|L\.?P\.?|LP|Ltd|Limited|Corp|Corporation|"
    r"Holdings?|HoldCo|Group|Co|N\.?V\.?|S\.?A\.?|GmbH|Plc)\.?$", re.I)


# OCSL sectors observed in identifiers (used as the issuer/sector
# boundary when the sector itself contains a comma is rare — we mainly
# rely on corp-suffix detection and "&" markers).
_OCSL_SECTORS = (
    "Application Software", "Biotechnology", "Distributors",
    "Diversified Support Services", "Health Care Services",
    "Interactive Media & Services", "Multi-Sector Holdings",
    "Oil & Gas Storage & Transportation",
    "Paper & Plastic Packaging Products & Materials",
    "Pharmaceuticals", "Real Estate Development",
    "Real Estate Operating Companies", "Specialized Finance",
    "Aerospace & Defense", "Air Freight & Logistics",
    "Banks", "Building Products", "Capital Markets", "Chemicals",
    "Commercial Services & Supplies", "Communications Equipment",
    "Construction & Engineering", "Construction Materials",
    "Consumer Finance", "Containers & Packaging",
    "Diversified Financial Services",
    "Diversified Telecommunication Services", "Electric Utilities",
    "Electrical Equipment", "Energy Equipment & Services",
    "Entertainment", "Food & Staples Retailing", "Food Products",
    "Health Care Equipment & Supplies",
    "Health Care Providers & Services", "Health Care Technology",
    "Hotels, Restaurants & Leisure", "Household Durables",
    "Household Products", "IT Services", "Insurance",
    "Internet & Direct Marketing Retail",
    "Life Sciences Tools & Services", "Machinery", "Media",
    "Metals & Mining", "Office Services & Supplies",
    "Oil, Gas & Consumable Fuels", "Paper & Forest Products",
    "Personal Products", "Professional Services",
    "Real Estate Management & Development",
    "Road & Rail", "Semiconductors & Semiconductor Equipment",
    "Software", "Specialty Retail",
    "Technology Hardware, Storage & Peripherals",
    "Textiles, Apparel & Luxury Goods",
    "Trading Companies & Distributors",
    "Transportation Infrastructure", "Water Utilities",
    "Wireless Telecommunication Services",
    "Electronic Equipment, Instruments & Components",
    "Independent Power and Renewable Electricity Producers",
)


@register
class Ocsl(Bdc):
    ticker = "OCSL"
    canonical_fv_m = 2838.0
    canonical_period = "2025-09-30"   # OCSL fiscal year ends Sept 30

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}
        # Try to peel "<Issuer>, <Sector>, <Type>" by recognizing a known
        # sector that ends a comma-bounded segment.
        for sect in sorted(_OCSL_SECTORS, key=len, reverse=True):
            marker = ", " + sect + ","
            if marker in ident:
                idx = ident.index(marker)
                out["entity"] = ident[:idx].strip(" ,")
                out["sector"] = sect
                tail = ident[idx + len(marker):].strip(" ,")
                if tail:
                    out["type"] = tail
                return out
            # Sector at the very end (no type marker)
            marker_end = ", " + sect
            if ident.endswith(marker_end):
                out["entity"] = ident[: -len(marker_end)].strip(" ,")
                out["sector"] = sect
                return out
        return out
