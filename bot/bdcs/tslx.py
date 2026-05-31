"""TSLX — Sixth Street Specialty Lending, Inc. (CIK 0001508655).

TSLX identifier shape:
  "<Section> <Sector> <Issuer> Investment <Type Description>
   (<par, due M/YYYY>) Initial Acquisition Date <D> Reference Rate and
   Spread <Base> + <X>% Interest Rate <X>% ..."

We use field markers ("Investment", "Initial Acquisition Date",
"Reference Rate and Spread", "Interest Rate") to slice the label.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register

_SECTION_RX = re.compile(
    r"^(?P<section>Debt Investments|Equity and Other Investments|"
    r"Equity Investments|Investment Funds|Warrant Investments|"
    r"Structured Credit Investments|Cash Equivalents|"
    r"Other Investments)\s+", re.I)
_TSLX_ACQ_RX = re.compile(
    r"Initial Acquisition Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", re.I)
_TSLX_SPREAD_RX = re.compile(
    r"Reference Rate and Spread\s+(SOFR|EURIBOR|SONIA|STIBOR|CDOR|"
    r"NIBOR|BBSY|TIBOR|Prime|LIBOR|[SEPL])\s*\+\s*([\d.]+)\s*%", re.I)
_TSLX_RATE_RX = re.compile(r"Interest Rate\s+([\d.]+)\s*%")
_TSLX_MAT_RX = re.compile(r"due\s+(\d{1,2}/\d{4})", re.I)


_TSLX_SECTORS = (
    "Aerospace & Defense", "Automobiles", "Banks", "Beverages",
    "Building Products", "Business Services", "Capital Markets",
    "Chemicals", "Commercial Services", "Communications",
    "Construction & Engineering", "Consumer & Household Products",
    "Consumer Products", "Consumer Services", "Containers & Packaging",
    "Diversified Consumer Services", "Diversified Financial Services",
    "Diversified Telecommunication Services",
    "Education Services", "Electric Utilities", "Electronic Equipment",
    "Energy", "Entertainment", "Financial Services",
    "Food & Beverage", "Food Products", "Healthcare", "Healthcare Equipment",
    "Healthcare Providers", "Healthcare Services",
    "Hotel, Gaming and Leisure", "Hotels, Restaurants and Leisure",
    "Human Resource Support Services", "Insurance Services",
    "Internet & Direct Marketing", "Internet Services",
    "IT Services", "Industrials", "Investment Services", "Logistics",
    "Machinery", "Manufacturing", "Marketing Services", "Media",
    "Office Services & Supplies",
    "Oil, Gas and Consumable Fuels", "Oil, Gas & Consumable Fuels",
    "Oil and Gas", "Pharmaceuticals", "Professional Services",
    "Real Estate", "Retail and Consumer Products", "Retail",
    "Road & Rail", "Software & Services", "Software", "Specialty Retail",
    "Technology Hardware", "Tobacco", "Transportation",
    "Utilities", "Wireless Telecommunication Services",
)


@register
class Tslx(Bdc):
    ticker = "TSLX"
    canonical_fv_m = 3313.4
    canonical_period = "2026-03-31"
    value_scale_m = 0.001

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}

        m = _SECTION_RX.match(ident)
        section = m.group("section") if m else ""
        s = ident[m.end():] if m else ident

        # Strip sector from start
        for sect in sorted(_TSLX_SECTORS, key=len, reverse=True):
            if s.startswith(sect + " "):
                out["sector"] = sect
                s = s[len(sect) + 1:]
                break

        # Issuer ends where the instrument type begins. Try multiple markers.
        idx = -1
        used_marker = ""
        for marker in (" Investment ", " First-lien loan", " First-Lien Loan",
                       " First-lien note", " First-lien revolving",
                       " Second-lien loan", " Second-Lien Loan",
                       " Second-lien note", " Second-lien revolving",
                       " First lien loan", " First lien note",
                       " Subordinated loan", " Subordinated note",
                       " Mezzanine note", " Mezzanine loan",
                       " Senior secured note", " Senior secured loan",
                       " Senior unsecured note", " Unsecured note",
                       " Convertible", " ABL FILO ",
                       " Roll Up DIP ", " Super-Priority DIP ", " DIP ",
                       " Term loan ", " Revolver",
                       " Preferred Stock", " Preferred Shares",
                       " Preferred Units", " Preferred",
                       " Common Stock", " Common Equity",
                       " Common Shares", " Common Units",
                       " Class A", " Class B", " Class C", " Class D",
                       " Class E", " Class AA", " Series ",
                       " Partnership Interest", " Partnership",
                       " Membership Interest", " LLC Interest",
                       " LP Interest", " Equity Interest",
                       " Earnout", " Ordinary", " Convertible Preferred",
                       " Trust Certif", " Units ",
                       " Warrant", " Structured Credit"):
            pos = s.find(marker)
            if pos > 0 and (idx < 0 or pos < idx):
                idx = pos
                used_marker = marker
        if idx > 0:
            out["entity"] = s[:idx].strip(" ,.")
            tail = s[idx:].lower()
            if "first-lien" in tail or "first lien" in tail:
                out["type"] = "First Lien"
            elif "second-lien" in tail or "second lien" in tail:
                out["type"] = "Second Lien"
            elif "preferred" in tail:
                out["type"] = "Preferred Equity"
            elif "common" in tail:
                out["type"] = "Common Equity"
            elif "warrant" in tail:
                out["type"] = "Warrant"
            elif "structured" in tail:
                out["type"] = "Structured Credit"
            elif "subordinated" in tail:
                out["type"] = "Subordinated"
            elif "mezzanine" in tail:
                out["type"] = "Mezzanine"
            elif "unsecured" in tail:
                out["type"] = "Unsecured"
            elif "abl filo" in tail or "dip " in tail or "term loan" in tail:
                out["type"] = "First Lien"

        if "warrant" in section.lower():
            out["type"] = "Warrant"
        elif "equity" in section.lower() and not out.get("type"):
            out["type"] = "Equity"

        # Acquisition date
        m = _TSLX_ACQ_RX.search(ident)
        if m:
            mo, dy, yr = m.group(1).split("/")
            yr_full = int(yr) if len(yr) == 4 else (
                2000 + int(yr) if int(yr) <= 50 else 1900 + int(yr))
            out["acq"] = f"{yr_full}-{int(mo):02d}-{int(dy):02d}"

        # Spread / base
        m = _TSLX_SPREAD_RX.search(ident)
        if m:
            base = m.group(1).upper()
            if base == "S":
                base = "SOFR"
            elif base == "E":
                base = "EURIBOR"
            elif base == "P":
                base = "Prime"
            out["base_rate"] = base
            out["spread"] = float(m.group(2))

        m = _TSLX_RATE_RX.search(ident)
        if m:
            out["rate"] = float(m.group(1))

        m = _TSLX_MAT_RX.search(ident)
        if m:
            mo, yr = m.group(1).split("/")
            out["maturity"] = f"{yr}-{int(mo):02d}"

        return out
