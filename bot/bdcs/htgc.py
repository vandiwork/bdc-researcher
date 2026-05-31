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
# Tranche-type marker segment (a comma-field that names the debt type).
_HTGC_TYPE_MARKER = re.compile(
    r"^(Senior Secured|Unsecured|Subordinated|Senior Subordinated|"
    r"Convertible|Second Lien|First Lien|Preferred|Common|Warrant)\b", re.I)
# Bare corporate suffix segment (so "AlphaSense" + "Inc." rejoin).
_HTGC_CORP_SUFFIX = re.compile(
    r"^(Inc\.?|LLC\.?|L\.?L\.?C\.?|Corp\.?|Corporation|Ltd\.?|Limited|"
    r"L\.?P\.?|N\.?V\.?|GmbH|AB|S\.?A\.?|Co\.?|Company|Holdings|plc|PLC)\.?$",
    re.I)


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
        parts = [p.strip() for p in ident.split(",")]
        section = parts[0].lower() if parts else ""

        # Anchor on the tranche-type marker segment.
        type_idx = None
        for i in range(2, len(parts)):
            if _HTGC_TYPE_MARKER.match(parts[i]):
                type_idx = i
                break

        if type_idx is not None:
            if type_idx >= 3 and _HTGC_CORP_SUFFIX.match(parts[type_idx - 1]):
                out["entity"] = f"{parts[type_idx - 2]}, {parts[type_idx - 1]}"
            else:
                out["entity"] = parts[type_idx - 1]
            type_marker = parts[type_idx]
        else:
            # Equity/warrant rows: issuer is the segment before the first
            # date/rate-looking field.
            ent = None
            for i in range(2, len(parts)):
                if re.search(r"\b(?:19|20)\d{2}\b|SOFR|Prime|FIXED|%", parts[i]):
                    if i - 1 >= 3 and _HTGC_CORP_SUFFIX.match(parts[i - 1]):
                        ent = f"{parts[i - 2]}, {parts[i - 1]}"
                    else:
                        ent = parts[i - 1]
                    break
            out["entity"] = ent or (parts[2] if len(parts) > 2 else parts[-1])
            type_marker = ""

        if "warrant" in section:
            out["type"] = "Warrant"
        elif "equity" in section:
            out["type"] = ("Preferred Equity" if "preferred" in ident.lower()
                           else "Common Equity")
        else:  # Debt Investments
            out["type"] = _normalize_type(type_marker) if type_marker else "First Lien"

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
