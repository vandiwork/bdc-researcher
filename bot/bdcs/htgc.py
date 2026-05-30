"""HTGC — Hercules Capital, Inc. (CIK 0001280784).

HTGC labels embed everything: section, sector, issuer, type, maturity,
base rate, and spread, joined by " and ":

    "Debt Investments Application Software and Alchemer LLC and
     Senior Secured and Maturity Date May 2028 and 1-month SOFR + ..."

The dashboard reports portfolio FV at the company level (~$4.5B); the
filer's per-tranche SOI sums slightly higher because HTGC writes
Term A/B/C/R + Revolvers + Warrants per company. We track the filer-
canonical total (un-segmented XBRL FV) which is $4,466.6M for FY2025.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register

_SECTION_RX = re.compile(
    r"^(?P<section>Debt Investments|Equity Investments|"
    r"Warrant Investments|Investment Funds?)\s+", re.I)
_SECTORS = [
    "Application Software", "Drug Discovery & Development",
    "Consumer & Business Services", "Healthcare Services",
    "System Software", "Communications", "Medical Devices & Equipment",
    "Information Services", "Internet Consumer & Business Services",
    "Surgical Devices", "Biotechnology Tools", "Diversified Financial Services",
    "Software (Internet, Mobile, Hardware)", "Diagnostic",
    "Sustainable and Renewable Technology", "Semiconductors",
    "Specialty Pharmaceuticals", "Media/Content/Info", "Electronics & Computer Hardware",
    "Energy Technology", "Consumer & Business Products",
]
_MATURITY_RX = re.compile(r"Maturity Date\s+([A-Za-z]+ \d{4})", re.I)
_BASE_RX = re.compile(r"\b(SOFR|SONIA|EURIBOR|Prime|LIBOR)\b", re.I)
_SPREAD_RX = re.compile(r"(?:SOFR|Prime|Base)[^\d]*?([0-9]+\.[0-9]+)\s*%", re.I)


_TOTAL_RX = re.compile(r"\b(?:and\s+)?Total\s+[A-Z]", re.I)


@register
class Htgc(Bdc):
    ticker = "HTGC"
    canonical_fv_m = 4722.0   # un-segmented XBRL total for 2025-12-31
    canonical_period = "2026-03-31"

    # HTGC tags issuer-level totals like "Debt Investments <Sector> and
    # Total <Issuer>, LLC" — these are roll-ups summing all tranches per
    # issuer. Drop them.
    drop_identifier_patterns = (_TOTAL_RX,)

    def parse_identifier(self, ident: str) -> dict:
        """HTGC identifier shape:
        "<Section> <Sector> and <Issuer> and <Tranche> and Maturity Date
         <Month YYYY> and <BaseRate> + <Spread>% [PIK ...]"

        We split on " and " (HTGC's field separator) — first segment is
        "<Section> <Sector>", second is the issuer, the rest are tranche
        details.
        """
        out: dict = {}
        s = ident
        m = _SECTION_RX.match(s)
        if m:
            sect = m.group("section").lower()
            if "warrant" in sect:
                out["type"] = "Warrant"
            elif "equity" in sect:
                out["type"] = "Equity"
            s = s[m.end():]

        # Split on " and " — HTGC's field separator
        parts = s.split(" and ")
        if len(parts) >= 2:
            # First part is the sector
            out["sector"] = parts[0].strip()
            # Second part is the issuer (strip trailing commas/footnotes)
            issuer = parts[1].strip().rstrip(",")
            out["entity"] = issuer
            # If a 3rd part looks like a type marker, capture it
            if len(parts) >= 3:
                tranche = parts[2].strip()
                if re.search(r"Senior Secured|Convertible|Subordinated|"
                             r"Preferred|Common|Warrant",
                             tranche, re.I):
                    out.setdefault("type", _normalize_type(tranche))

        m = _MATURITY_RX.search(ident)
        if m:
            out["maturity"] = m.group(1)
        m = _BASE_RX.search(ident)
        if m:
            out["base_rate"] = m.group(1).upper()
        m = _SPREAD_RX.search(ident)
        if m:
            out["spread"] = float(m.group(1))
        return out


def _normalize_type(text: str) -> str:
    """Map HTGC tranche text to canonical type."""
    t = text.lower()
    if "warrant" in t: return "Warrant"
    if "preferred" in t: return "Preferred Equity"
    if "common" in t: return "Common Equity"
    if "subordinated" in t: return "Subordinated"
    if "convertible" in t: return "Convertible"
    if "senior secured" in t: return "First Lien"
    return text.strip()
