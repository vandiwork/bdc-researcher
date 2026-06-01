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

# Unambiguous terminal corporate suffixes, used to find where MFIC's
# "<portfolio company> <legal entity>" concatenation splits. Deliberately
# excludes short/ambiguous ones (AG, AB, Oy, S.A) that match inside acronyms
# such as "EVER.AG".
_TERM_SUFFIX = (r"L\.?L\.?C\.?|Inc\.?|Incorporated|Corp\.?|Corporation|"
                r"L\.?P\.?|LLP|Ltd\.?|Limited|PLC|GmbH")
_MID_SUFFIX_RX = re.compile(
    r"(?:^|\s)(?:" + _TERM_SUFFIX + r")\.?,?\s+(?=[A-Z0-9])")
_END_SUFFIX_RX = re.compile(r"\b(?:" + _TERM_SUFFIX + r")\.?\)?\s*$", re.I)


def _norm_tok(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _split_brand_legal(head: str) -> tuple[str, str]:
    """MFIC packs "<portfolio company> <legal investment entity>" into one
    identifier string with no delimiter (e.g. "Primeflight PrimeFlight
    Acquisition, LLC", "AVAD, LLC Surf Opco, LLC"). Return (brand, legal);
    brand is "" when we can't confidently split (i.e. it's a single name)."""
    # Drop former-name / alias parentheticals ("(f/k/a …)", "(fka …)",
    # "(d/b/a …)") first — they sit MID-string in MFIC identifiers and would
    # otherwise be split through, orphaning a ")" (e.g. "Renew Financial LLC
    # (f/k/a Renewable Funding, LLC) AIC SPV Holdings II, LLC").
    head = re.sub(r"\s*\((?:f/?k/?a|d/?b/?a|a/?k/?a|fka|dba|aka|formerly)\b[^)]*\)",
                  "", head, flags=re.I)
    head = re.sub(r"\s{2,}", " ", head).strip()
    words = head.split()
    # Rule 1: the legal name restarts with a token sharing the brand's first
    # word ("Primeflight PrimeFlight…", "Pro Vigil Pro-Vigil…",
    # "Sperry Acquisition, LLC Sperry Parent…").
    if len(words) >= 2 and len(_norm_tok(words[0])) >= 3:
        n0 = _norm_tok(words[0])
        for i in range(1, len(words)):
            ni = _norm_tok(words[i])
            if len(ni) >= 3 and (ni.startswith(n0) or n0.startswith(ni)):
                brand = " ".join(words[:i]).strip(" ,.")
                legal = " ".join(words[i:]).strip(" ,.")
                if re.search(r"[A-Za-z]", legal) and _norm_tok(brand) != _norm_tok(legal):
                    return brand, legal
                break
    # Rule 2: the brand name ends in a whole-token terminal suffix and the tail
    # is itself a suffixed company name ("AVAD, LLC Surf Opco, LLC",
    # "Calero Holdings, Inc. Telesoft Holdings, LLC").
    for m in _MID_SUFFIX_RX.finditer(head):
        tail = head[m.end():].strip(" ,.")
        if (tail and not tail.startswith("(") and len(tail) >= 4
                and _END_SUFFIX_RX.search(tail)):
            return head[:m.end()].strip(" ,."), tail
    return "", head

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
    "Personal Care Products", "Personal Products",
    "Paper & Forest Products", "Health Care Providers & Service",
    "Pharmaceuticals",
    "Professional Services", "Real Estate Management & Development",
    "Semiconductors & Semiconductor Equipment",
    "Software", "Specialty Retail",
    "Technology Hardware, Storage & Peripherals",
    "Textiles, Apparel & Luxury Goods",
    "Trading Companies & Distributors",
    "Transportation Infrastructure", "Ground Transportation",
    "Passenger Airlines", "Consumer Staples Distribution & Retail",
    "Wireless Telecommunication Services",
    "Independent Power and Renewable Electricity Producers",
)


@register
class Mfic(Bdc):
    ticker = "MFIC"
    canonical_fv_m = 2971.5
    canonical_period = "2026-03-31"

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

        # MFIC concatenates the portfolio-company (brand) name and the legal
        # investment entity with no delimiter, e.g.:
        #   "Sperry Acquisition, LLC Sperry Parent Holdings, L.P"
        #   "Primeflight PrimeFlight Acquisition, LLC"
        #   "AVAD, LLC Surf Opco, LLC"
        # Split them and file the brand as a (dba …) so apply_names surfaces
        # the legal entity as the main name and the brand as the grey line.
        head = re.sub(r"\s{2,}", " ", head).strip()
        brand, legal = _split_brand_legal(head)
        if brand:
            out["entity"] = f"{legal} (dba {brand})"
        else:
            out["entity"] = head.strip(" ,.")

        m = _SPREAD_RX.search(ident)
        if m:
            out["spread"] = int(m.group(1)) / 100.0
            out["base_rate"] = "SOFR"
        return out
