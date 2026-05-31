"""TCPC — BlackRock TCP Capital Corp (CIK 0001370755).

Identifier labels embed everything inline:
    "<Section> <Sector> <Issuer> <Type> Ref <Base>(<Freq>)
     Floor <Floor>% Spread <Spread>% Total <Rate>% Maturity <Date>"

The 91 "Debt" / 16 "Equity" lone-prefix rows are sub-SOI roll-ups from
TCPC's consolidated subsidiary Special Value Continuation Fund (SVCF) —
they have no detailed metadata and are dropped via prefix.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register

_SECTION_RX = re.compile(
    r"^(?:Debt Investments|Equity Securities|Warrant Investments|"
    r"Controlled Affiliates|Non-Controlled Affiliates|Investment Funds)\s+", re.I)
_TYPE_KEYWORDS = [
    ("First Lien",          re.compile(r"First Lien", re.I)),
    ("Second Lien",         re.compile(r"Second Lien", re.I)),
    ("Senior Subordinated", re.compile(r"Senior Subordinated", re.I)),
    ("Subordinated",        re.compile(r"\bSubordinated\b", re.I)),
    ("Preferred Equity",    re.compile(r"Preferred|Series\s+[A-Z0-9][\w-]*\s+Shares", re.I)),
    ("Warrant",             re.compile(r"\bWarrant", re.I)),
    ("Common Equity",       re.compile(r"Common\s+(?:Stock|Equity|Units?|Shares)", re.I)),
    ("Equity",              re.compile(r"Limited Partnership|Limited Liability|\b(?:Equity|Stock|Units?|Interests?)\b", re.I)),
]
_SPREAD_RX = re.compile(r"Spread\s+([0-9]+\.[0-9]+)\s*%", re.I)
_RATE_RX = re.compile(r"Total\s+([0-9]+\.[0-9]+)\s*%", re.I)
_FLOOR_RX = re.compile(r"Floor\s+([0-9]+\.[0-9]+)\s*%", re.I)
_BASE_RX = re.compile(r"\b(SOFR|SONIA|EURIBOR|Prime)\b", re.I)
_MATURITY_RX = re.compile(r"Maturity\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)


@register
class Tcpc(Bdc):
    ticker = "TCPC"
    canonical_fv_m = 1388.7
    canonical_period = "2026-03-31"

    drop_identifier_exact = frozenset({
        "Debt", "Equity", "Warrant Investments",
    })
    # Redundant "Controlled Affiliates, ..." and "Non-Controlled Affiliates, ..."
    # rows duplicate the sector-led canonical labels. Drop them.
    drop_identifier_prefixes = (
        "Controlled Affiliates,",
        "Non-Controlled Affiliates,",
    )

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}
        m = _SECTION_RX.match(ident)
        s = ident[m.end():] if m else ident
        # Try to strip a known sector from the start
        for sect in sorted(_TCPC_SECTORS, key=len, reverse=True):
            if s.startswith(sect + " "):
                out["sector"] = sect
                s = s[len(sect) + 1:]
                break
        # Issuer ends at the EARLIEST type/instrument/descriptor marker. Equity
        # rows often have no loan-style type keyword (e.g. "... Common Shares",
        # "... Series X Shares", "... Limited Partnership/Limited Liability
        # Company Interests"); we still delimit the issuer so the section/sector
        # prefix never leaks into the name via the generic fallback.
        cut = len(s)
        best = None
        for tname, rx in _TYPE_KEYWORDS:
            tm = rx.search(s)
            if tm and tm.start() < cut:
                cut = tm.start()
                best = tname
        if best:
            out["type"] = best
        for marker in (" Senior Note ", " Sr Secured ", " Membership Units",
                       " Ref ", " Term Loan ", " ("):
            idx = s.find(marker)
            if 0 < idx < cut:
                cut = idx
        out["entity"] = s[:cut].strip(" ,.")
        m = _SPREAD_RX.search(ident)
        if m: out["spread"] = float(m.group(1))
        m = _RATE_RX.search(ident)
        if m: out["rate"] = float(m.group(1))
        m = _BASE_RX.search(ident)
        if m: out["base_rate"] = m.group(1).upper()
        m = _MATURITY_RX.search(ident)
        if m:
            try:
                mo, dy, yr = m.group(1).split("/")
                out["maturity"] = f"{yr}-{int(mo):02d}-{int(dy):02d}"
            except ValueError:
                pass
        return out


_TCPC_SECTORS = (
    "Aerospace & Defense", "Aerospace and Defense",
    "Automobiles", "Banking", "Building Products",
    "Capital Markets", "Chemicals", "Commercial Services & Supplies",
    "Commercial Services and Supplies", "Construction & Engineering",
    "Construction and Engineering", "Consumer Finance",
    "Containers & Packaging", "Containers and Packaging",
    "Diversified Consumer Services", "Diversified Consumer Service",
    "Diversified Financial Services",
    "Insurance", "Trading Companies & Distributors",
    "Internet and Catalog Retail", "Internet & Catalog Retail",
    "Oil, Gas and Consumable Fuels",
    "Electrical Equipment", "Electric Utilities",
    "Energy Equipment & Services", "Energy Equipment and Services",
    "Health Care Equipment & Supplies", "Health Care Providers & Services",
    "Health Care Providers and Services", "Health Care Technology",
    "Healthcare Providers and Services", "Hotels, Restaurants & Leisure",
    "Hotels, Restaurants and Leisure",
    "Internet Software & Services", "Internet Software and Services",
    "IT Services", "Life Sciences Tools & Services",
    "Life Sciences Tools and Services", "Machinery", "Media",
    "Oil, Gas & Consumable Fuels", "Paper & Forest Products",
    "Paper and Forest Products", "Pharmaceuticals",
    "Professional Services", "Real Estate Management & Development",
    "Real Estate Management and Development", "Road & Rail", "Road and Rail",
    "Semiconductors & Semiconductor Equipment",
    "Semiconductors and Semiconductor Equipment",
    "Software", "Specialty Retail",
    "Technology Hardware, Storage & Peripherals",
    "Textiles, Apparel & Luxury Goods", "Textiles, Apparel and Luxury Goods",
    "Wireless Telecommunication Services",
)
