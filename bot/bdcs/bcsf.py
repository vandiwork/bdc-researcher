"""BCSF — Bain Capital Specialty Finance, Inc. (CIK 0001655050).

The 10-K embeds full sub-SOIs for two joint ventures
(Bain Capital Senior Loan Program LLC and International Senior Loan
Program LLC) tagged with `us-gaap:InvestmentCompanyNonconsolidatedSubsidiaryAxis`.
The base class's allowed_position_dims filter excludes those contexts,
bringing BCSF to the dashboard FV exactly.

Identifier labels embed sector, type, base rate, spread, rate, and
maturity, e.g.:
    "Non-controlled/Non-Affiliated Investments Beverage, Food & Tobacco
     SauceCo HoldCo, LLC First Lien Senior Secured Loan SOFR Spread
     5.75% Interest Rate 9.42% Maturity Date 5/13/2030"
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


_SECTORS = [
    "Aerospace & Defense", "Automotive", "Banking, Finance, Insurance & Real Estate",
    "Beverage, Food & Tobacco", "Capital Equipment", "Chemicals, Plastics & Rubber",
    "Construction & Building", "Consumer Goods: Durable", "Consumer Goods: Non-Durable",
    "Containers, Packaging & Glass", "Energy: Oil & Gas",
    "FIRE: Finance", "FIRE: Insurance", "FIRE: Real Estate",
    "Healthcare & Pharmaceuticals", "High Tech Industries", "Hotel, Gaming & Leisure",
    "Investment Vehicles", "Legacy Corporate Lending",
    "Media: Advertising, Printing & Publishing", "Media: Broadcasting & Subscription",
    "Media: Diversified & Production", "Metals & Mining", "Retail",
    "Services: Business", "Services: Consumer", "Telecommunications",
    "Transportation: Cargo", "Transportation: Consumer", "Utilities: Electric",
    "Utilities: Oil & Gas", "Utilities: Water", "Wholesale",
]

_PFX = re.compile(
    r"^(?:Non-controlled/Non-Affiliated|Non-Controlled/Affiliated|Controlled Affiliate)"
    r"\s+Investments\s+", re.I)
_CCY = re.compile(
    r"^(British Pound|Euro|Canadian Dollar|Australian Dollar|"
    r"Swiss Franc|Singapore Dollar|New Zealand Dollar|Danish Krone|"
    r"Swedish Krona|Norwegian Krone)\s+", re.I)
_SPREAD = re.compile(r"Spread\s+([0-9]+\.[0-9]+)%", re.I)
_RATE = re.compile(r"Interest Rate\s+([0-9]+\.[0-9]+)%", re.I)
_MATURITY = re.compile(r"Maturity Date\s+(\d{1,2}/\d{1,2}/\d{4})")
_BASE = re.compile(
    r"\b(SOFR|SONIA|EURIBOR|CDOR|TIBOR|BBSY|STIBOR|NIBOR|CIBOR|BKBM|Prime)\b", re.I)
_TYPE_RX = [
    ("First Lien",          re.compile(r"First Lien", re.I)),
    ("Second Lien",         re.compile(r"Second Lien", re.I)),
    ("Senior Subordinated", re.compile(r"Senior Subordinated", re.I)),
    ("Subordinated",        re.compile(r"\bSubordinated\b", re.I)),
    ("Preferred Equity",    re.compile(r"Preferred (?:Equity|Stock|Interest|Units?)", re.I)),
    ("Warrant",             re.compile(r"\bWarrant", re.I)),
    ("Common Equity",       re.compile(r"Common (?:Equity|Stock|Units?)", re.I)),
    ("Equity",              re.compile(r"\bEquity Interest", re.I)),
]
_CURRENCY_CODE = {
    "British Pound": "GBP", "Euro": "EUR", "Canadian Dollar": "CAD",
    "Australian Dollar": "AUD", "Swiss Franc": "CHF",
    "Singapore Dollar": "SGD", "New Zealand Dollar": "NZD",
    "Danish Krone": "DKK", "Swedish Krona": "SEK", "Norwegian Krone": "NOK",
}


@register
class Bcsf(Bdc):
    ticker = "BCSF"
    canonical_fv_m = 2509.0
    canonical_period = "2025-12-31"

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}
        s = ident
        # Affiliation prefix
        m = _PFX.match(s)
        if m:
            s = s[m.end():]
        # Currency prefix
        m = _CCY.match(s)
        if m:
            out["ccy"] = _CURRENCY_CODE.get(m.group(1).title(), "USD")
            s = s[m.end():]
        # Sector
        for sec in _SECTORS:
            if s.startswith(sec):
                out["sector"] = sec
                s = s[len(sec):].lstrip()
                break
        # Spread / rate / maturity / base rate
        m = _SPREAD.search(ident)
        if m: out["spread"] = float(m.group(1))
        m = _RATE.search(ident)
        if m: out["rate"] = float(m.group(1))
        m = _MATURITY.search(ident)
        if m:
            try:
                mo, dy, yr = m.group(1).split("/")
                out["maturity"] = f"{yr}-{int(mo):02d}-{int(dy):02d}"
            except (ValueError, IndexError):
                pass
        m = _BASE.search(ident)
        if m: out["base_rate"] = m.group(1).upper()
        # Type and entity
        for tname, rx in _TYPE_RX:
            tm = rx.search(s)
            if tm:
                out["type"] = tname
                out["entity"] = s[:tm.start()].strip(" ,.")
                break
        else:
            out["entity"] = s.strip(" ,.")
        return out
