"""GSBD — Goldman Sachs BDC, Inc. (CIK 0001572694).

GSBD's XBRL identifier packs everything into one label:
  "Investment Debt Investments - 216.4% United States - 205.6%
   1st Lien/Senior Secured Debt - 195.3% Zarya HoldCo, Inc. (dba Eptura)
   Industry Real Estate Mgmt. & Development Interest Rate 10.32%
   Reference Rate and Spread S + 6.50% Maturity 07/01/27"

We split on the field markers ("Industry", "Interest Rate", "Reference
Rate and Spread", "Maturity") to extract each piece.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


# Field markers in GSBD identifiers (in order they typically appear)
_MARKERS = [
    ("industry", re.compile(r"\bIndustry\s+(.+?)(?=\s+Interest Rate\s|\s+Reference Rate\s|\s+Maturity\s|$)")),
    ("rate", re.compile(r"\bInterest Rate\s+([\d.]+)\s*%")),
    ("spread_info", re.compile(r"\bReference Rate and Spread\s+([^M]+?)(?=\s+Maturity\s|$)")),
    ("maturity", re.compile(r"\bMaturity\s+(\d{1,2}/\d{1,2}/\d{2,4})")),
]


@register
class Gsbd(Bdc):
    ticker = "GSBD"
    canonical_fv_m = 3228.9
    canonical_period = "2026-03-31"

    def parse_identifier(self, ident: str) -> dict:
        out: dict = {}
        # Step 0: investment type from the section path. GSBD's section
        # header names the tranche type, e.g. "1st Lien/Senior Secured
        # Debt", "2nd Lien", "Unsecured Debt", "Preferred Stock", "Common
        # Stock", "Equity", "Warrants". Read it BEFORE the entity so the
        # generic splitter (which mis-reads "Interest Rate" as an equity
        # "interest") never has to run.
        idx_e = ident.find(" Industry ")
        tl = (ident[:idx_e] if idx_e > 0 else ident).lower()
        if re.search(r"1st lien|first lien|senior secured|unitranche", tl):
            out["type"] = "First Lien"
        elif re.search(r"2nd lien|second lien", tl):
            out["type"] = "Second Lien"
        elif "senior subordinated" in tl:
            out["type"] = "Senior Subordinated"
        elif re.search(r"mezzanine|subordinated", tl):
            out["type"] = "Subordinated"
        elif "unsecured" in tl:
            out["type"] = "Unsecured"
        elif "warrant" in tl:
            out["type"] = "Warrant"
        elif "preferred" in tl:
            out["type"] = "Preferred Equity"
        elif re.search(r"common (?:stock|equity|units?)|\bequity\b", tl):
            out["type"] = "Common Equity"
        # Step 1: extract field markers from the right side
        for field, rx in _MARKERS:
            m = rx.search(ident)
            if not m:
                continue
            if field == "industry":
                out["sector"] = m.group(1).strip()
            elif field == "rate":
                out["rate"] = float(m.group(1))
            elif field == "spread_info":
                txt = m.group(1).strip()
                # e.g. "S + 6.50%"
                bm = re.match(r"([SEPL])\s*\+\s*([\d.]+)", txt, re.I)
                if bm:
                    out["base_rate"] = {"S": "SOFR", "E": "EURIBOR",
                                         "P": "Prime", "L": "LIBOR"}.get(
                        bm.group(1).upper(), bm.group(1).upper())
                    out["spread"] = float(bm.group(2))
            elif field == "maturity":
                mo, dy, yr = m.group(1).split("/")
                yr_full = int(yr) if len(yr) == 4 else (2000 + int(yr) if int(yr) <= 50 else 1900 + int(yr))
                out["maturity"] = f"{yr_full}-{int(mo):02d}-{int(dy):02d}"

        # Step 2: cut identifier at first marker to isolate section+issuer
        head = ident
        for kw in ("Industry ", "Interest Rate ", "Reference Rate "):
            idx = head.find(kw)
            if idx > 0:
                head = head[:idx].rstrip()
                break

        # Step 3: strip the section path (sequence of "X - N%" sections)
        cleaned = head
        # Strip iteratively the LAST section that ends with "% " — but only
        # if it looks like a section header (contains "Lien", "Investments",
        # country name, etc.)
        section_words = (
            "Investment Debt Investments", "Investment Equity Investments",
            "Investment Equity Securities", "Investment Equity",
            "Investment Warrant Investments", "Investment Warrants",
            "Investments Debt Investments", "Investments Equity Investments",
            "Debt Investments", "Equity Investments", "Warrant Investments",
            "Equity Securities", "Warrants",
            "1st Lien", "2nd Lien", "First Lien", "Second Lien",
            "Senior Secured", "Senior Subordinated", "Subordinated",
            "Senior Notes", "Mezzanine", "Common Stock", "Preferred Stock",
            "Unsecured Debt", "Unsecured Notes", "Convertible",
            "Equity",
            # Countries (case-insensitive — these appear in section headers)
            "United States", "Canada", "United Kingdom", "Bermuda",
            "Cayman Islands", "Israel", "Australia", "Germany", "France",
            "Switzerland", "Ireland", "Netherlands", "Luxembourg",
            "Sweden", "Norway", "Denmark", "Finland", "Spain", "Italy",
            "Belgium", "Austria", "Japan", "South Korea", "Singapore",
            "India", "Brazil", "Mexico", "Argentina", "New Zealand",
            "China", "Hong Kong", "Taiwan", "Indonesia", "Malaysia",
            "Philippines", "Vietnam", "Thailand", "South Africa",
            "Czech Republic", "Poland", "Hungary", "Romania", "Greece",
        )
        # Walk through pattern "<section words> - X.X%" and strip
        for _ in range(8):
            # Find earliest match of "<known section> ... NN.N%"
            best = None
            for sw in section_words:
                rx = re.compile(re.escape(sw) + r"[^%]*?\d+(?:\.\d+)?\s*%\s*")
                m = rx.match(cleaned)
                if m:
                    if best is None or m.end() > best:
                        best = m.end()
            if best is None:
                break
            cleaned = cleaned[best:].lstrip()

        # Cleanup any residual "% " prefix
        cleaned = re.sub(r"^[\d.]+\s*%\s*", "", cleaned).strip()
        if cleaned and cleaned != ident:
            out["entity"] = cleaned
        return out
