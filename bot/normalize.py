"""Canonical taxonomy normalizers for BDC SOI data.

BDCs report sectors using a variety of taxonomies — GICS sub-industries,
Moody's industry codes ("Healthcare & Pharmaceuticals" / "FIRE: Finance"),
and ad-hoc industry names. We map them to two canonical levels:

  - `gics_sector`        : 11 GICS sectors + 2 BDC-specific
  - `gics_industry_group`: ~25 GICS industry groups

Security types vary similarly ("First Lien", "First lien senior secured
loan", "One stop", "Secured Debt", etc.). We map them to:

  - `type_canonical` : 10 standard BDC instrument categories

Both normalizers are case-insensitive and use ordered regex matching.
First match wins, so put more specific patterns before generic fallbacks.
"""
from __future__ import annotations

import re
from typing import Optional


# ── Canonical security types ─────────────────────────────────────────

# Maps raw type text → canonical bucket. Ordered: more specific first.
TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Structured credit / CLO
    (re.compile(r"\bCLO\b", re.I), "Structured Credit"),
    (re.compile(r"structured (?:secured )?note", re.I), "Structured Credit"),
    (re.compile(r"subordinated structured", re.I), "Structured Credit"),
    # Warrant
    (re.compile(r"\bwarrant", re.I), "Warrant"),
    # Investment fund interests
    (re.compile(r"\b(?:LLC|LP|Limited partnership)\s+(?:interest|unit)", re.I),
     "Common Equity"),
    (re.compile(r"(?:member|membership)\s+(?:interest|unit)", re.I),
     "Common Equity"),
    (re.compile(r"partnership (?:unit|interest|equity)", re.I), "Common Equity"),
    # Preferred equity — before Common
    (re.compile(r"preferred\s+(?:stock|equity|units?|shares?|interests?)", re.I),
     "Preferred Equity"),
    (re.compile(r"\bpreferred\b", re.I), "Preferred Equity"),
    # Common equity
    (re.compile(r"common\s+(?:stock|equity|units?|shares?|interests?)", re.I),
     "Common Equity"),
    (re.compile(r"\bclass\s+[A-Z][-0-9]*\s+(?:units?|shares?|stock|common|interest)", re.I),
     "Common Equity"),
    (re.compile(r"\bequity\s+interest", re.I), "Common Equity"),
    (re.compile(r"\bequity\s+investment", re.I), "Common Equity"),
    # Unitranche / One stop (GBDC) — aggregate into First Lien
    (re.compile(r"\bone[\s\-]?stop\b", re.I), "First Lien"),
    (re.compile(r"\bunitranche\b", re.I), "First Lien"),
    # Second lien
    (re.compile(r"second[\s\-]?lien|2nd[\s\-]?lien", re.I), "Second Lien"),
    # Senior subordinated / mezzanine
    (re.compile(r"senior\s+subordinated", re.I), "Subordinated"),
    (re.compile(r"\bmezzanine\b", re.I), "Mezzanine"),
    (re.compile(r"subordinated", re.I), "Subordinated"),
    # First lien (also catches: term loan, revolver, DIP, ABL FILO)
    (re.compile(r"first[\s\-]?lien|1st[\s\-]?lien", re.I), "First Lien"),
    (re.compile(r"\bsenior\s+secured\b", re.I), "First Lien"),
    (re.compile(r"\bsr\.?\s*secured\b", re.I), "First Lien"),
    (re.compile(r"\bDIP\b", re.I), "First Lien"),
    (re.compile(r"\bABL\s+FILO\b", re.I), "First Lien"),
    (re.compile(r"\b(?:term\s+loan|revolver|revolving|delayed\s+draw)\b", re.I),
     "First Lien"),
    (re.compile(r"\bfirst\s+out\b", re.I), "First Lien"),
    # Unsecured / senior notes
    (re.compile(r"\bunsecured\b", re.I), "Unsecured"),
    (re.compile(r"\bsenior\s+notes?\b", re.I), "Unsecured"),
    # Bonds, fixed-rate
    (re.compile(r"\b(?:fixed[\-\s]?rate|floating[\-\s]?rate)\s+(?:bond|note)",
                re.I), "Unsecured"),
    # Catchalls
    (re.compile(r"\bsecured\s+debt\b", re.I), "First Lien"),
    (re.compile(r"\b(?:bond|note)s?\b", re.I), "Unsecured"),
    (re.compile(r"^\s*Equity\s*$", re.I), "Common Equity"),
    (re.compile(r"^\s*(?:stock|units?)\s*$", re.I), "Common Equity"),
]


def normalize_type(raw: str) -> str:
    """Map a raw security-type string to a canonical bucket.

    Returns one of: First Lien, Second Lien, Subordinated, Mezzanine,
    Unsecured, Preferred Equity, Common Equity, Warrant, Structured
    Credit, Other.

    Unitranche / "One stop" loans are aggregated into First Lien — they
    sit at the top of the cap stack with senior security in practice.
    """
    if not raw:
        return "Other"
    text = raw.strip()
    for rx, canonical in TYPE_PATTERNS:
        if rx.search(text):
            return canonical
    return "Other"


# ── Canonical sectors (GICS sector + industry group) ─────────────────

# Map raw sector → (gics_sector, gics_industry_group).
# Use lowercase keys; we'll lowercase incoming text before lookup.
# Each entry can also be a regex pattern (compiled).
# Order matters for regex matches — more specific first.

GICS_SECTOR_MAP: dict[str, tuple[str, str]] = {
    # ── Communication Services ──
    "communication services": ("Communication Services", "Telecommunication Services"),
    "telecommunications": ("Communication Services", "Telecommunication Services"),
    "diversified telecommunication services": ("Communication Services", "Telecommunication Services"),
    "wireless telecommunication services": ("Communication Services", "Telecommunication Services"),
    "telecommunications: wireless": ("Communication Services", "Telecommunication Services"),
    "media": ("Communication Services", "Media & Entertainment"),
    "media & entertainment": ("Communication Services", "Media & Entertainment"),
    "media and entertainment": ("Communication Services", "Media & Entertainment"),
    "media: advertising, printing & publishing": ("Communication Services", "Media & Entertainment"),
    "media: broadcasting & subscription": ("Communication Services", "Media & Entertainment"),
    "media: diversified & production": ("Communication Services", "Media & Entertainment"),
    "media/content/info": ("Communication Services", "Media & Entertainment"),
    "entertainment": ("Communication Services", "Media & Entertainment"),
    "interactive media & services": ("Communication Services", "Media & Entertainment"),
    "interactive media and services": ("Communication Services", "Media & Entertainment"),
    "publishing": ("Communication Services", "Media & Entertainment"),
    "advertising": ("Communication Services", "Media & Entertainment"),
    "broadcasting": ("Communication Services", "Media & Entertainment"),
    "movies & entertainment": ("Communication Services", "Media & Entertainment"),
    "sports, media and entertainment": ("Communication Services", "Media & Entertainment"),

    # ── Consumer Discretionary ──
    "automobiles": ("Consumer Discretionary", "Automobiles & Components"),
    "automobiles and components": ("Consumer Discretionary", "Automobiles & Components"),
    "automobiles & components": ("Consumer Discretionary", "Automobiles & Components"),
    "automobile components": ("Consumer Discretionary", "Automobiles & Components"),
    "auto components": ("Consumer Discretionary", "Automobiles & Components"),
    "automotive": ("Consumer Discretionary", "Automobiles & Components"),
    "automotive components": ("Consumer Discretionary", "Automobiles & Components"),
    "consumer durables": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "consumer durables and apparel": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "household durables": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "leisure products": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "textiles, apparel & luxury goods": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "textiles, apparel and luxury goods": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "apparel": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "consumer goods: durable": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "consumer & household products": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "consumer products": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "consumer & business products": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "consumer services": ("Consumer Discretionary", "Consumer Services"),
    "diversified consumer services": ("Consumer Discretionary", "Consumer Services"),
    "hotels, restaurants & leisure": ("Consumer Discretionary", "Consumer Services"),
    "hotels, restaurants and leisure": ("Consumer Discretionary", "Consumer Services"),
    "hotel, gaming and leisure": ("Consumer Discretionary", "Consumer Services"),
    "services: consumer": ("Consumer Discretionary", "Consumer Services"),
    "education services": ("Consumer Discretionary", "Consumer Services"),
    "retailing": ("Consumer Discretionary", "Retailing"),
    "retail": ("Consumer Discretionary", "Retailing"),
    "specialty retail": ("Consumer Discretionary", "Retailing"),
    "internet & direct marketing": ("Consumer Discretionary", "Retailing"),
    "internet & direct marketing retail": ("Consumer Discretionary", "Retailing"),
    "multiline retail": ("Consumer Discretionary", "Retailing"),
    "retail and consumer products": ("Consumer Discretionary", "Retailing"),
    "distributors": ("Consumer Discretionary", "Retailing"),

    # ── Consumer Staples ──
    "food & staples retailing": ("Consumer Staples", "Food & Staples Retailing"),
    "consumer staples distribution": ("Consumer Staples", "Food & Staples Retailing"),
    "consumer staples distribution & retail": ("Consumer Staples", "Food & Staples Retailing"),
    "food products": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "food and beverage": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "food & beverage": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "beverages": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "beverage, food & tobacco": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "tobacco": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "household products": ("Consumer Staples", "Household & Personal Products"),
    "household and personal products": ("Consumer Staples", "Household & Personal Products"),
    "personal products": ("Consumer Staples", "Household & Personal Products"),

    # ── Energy ──
    "energy": ("Energy", "Energy"),
    "energy equipment & services": ("Energy", "Energy"),
    "energy equipment and services": ("Energy", "Energy"),
    "energy: oil & gas": ("Energy", "Energy"),
    "oil & gas storage & transportation": ("Energy", "Energy"),
    "oil, gas & consumable fuels": ("Energy", "Energy"),
    "oil and gas": ("Energy", "Energy"),
    "oil & gas": ("Energy", "Energy"),
    "energy technology": ("Energy", "Energy"),
    "energy: electricity": ("Energy", "Energy"),

    # ── Financials ──
    "banks": ("Financials", "Banks"),
    "banking": ("Financials", "Banks"),
    "thrifts & mortgage finance": ("Financials", "Banks"),
    "diversified financials": ("Financials", "Diversified Financials"),
    "diversified financial services": ("Financials", "Diversified Financials"),
    "financial services": ("Financials", "Diversified Financials"),
    "consumer finance": ("Financials", "Diversified Financials"),
    "capital markets": ("Financials", "Diversified Financials"),
    "investment services": ("Financials", "Diversified Financials"),
    "specialized finance": ("Financials", "Diversified Financials"),
    "structured finance": ("Financials", "Diversified Financials"),
    "fire: finance": ("Financials", "Diversified Financials"),
    "banking, finance, insurance, & real estate": ("Financials", "Diversified Financials"),
    "insurance": ("Financials", "Insurance"),
    "insurance services": ("Financials", "Insurance"),
    "fire: insurance": ("Financials", "Insurance"),
    "mortgage real estate investment trusts (reits)": ("Financials", "Diversified Financials"),

    # ── Health Care ──
    "healthcare": ("Health Care", "Health Care Equipment & Services"),
    "health care": ("Health Care", "Health Care Equipment & Services"),
    "health care equipment & supplies": ("Health Care", "Health Care Equipment & Services"),
    "health care equipment and supplies": ("Health Care", "Health Care Equipment & Services"),
    "healthcare equipment & supplies": ("Health Care", "Health Care Equipment & Services"),
    "healthcare equipment and supplies": ("Health Care", "Health Care Equipment & Services"),
    "health care equipment": ("Health Care", "Health Care Equipment & Services"),
    "healthcare equipment": ("Health Care", "Health Care Equipment & Services"),
    "medical devices & equipment": ("Health Care", "Health Care Equipment & Services"),
    "surgical devices": ("Health Care", "Health Care Equipment & Services"),
    "health care providers & services": ("Health Care", "Health Care Equipment & Services"),
    "health care providers and services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare providers & services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare providers and services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare providers": ("Health Care", "Health Care Equipment & Services"),
    "health care services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare services, other": ("Health Care", "Health Care Equipment & Services"),
    "health care technology": ("Health Care", "Health Care Equipment & Services"),
    "healthcare technology": ("Health Care", "Health Care Equipment & Services"),
    "health care equipment & services": ("Health Care", "Health Care Equipment & Services"),
    "health care equipment and services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare equipment and services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare equipment & services": ("Health Care", "Health Care Equipment & Services"),
    "healthcare & pharmaceuticals": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "pharmaceuticals": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "specialty pharmaceuticals": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "biotechnology": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "biotechnology tools": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "life sciences tools & services": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "life sciences tools and services": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "drug discovery & development": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "drug discovery and development": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "diagnostic": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "pharmaceuticals, biotechnology and life sciences": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),

    # ── Industrials ──
    "industrials": ("Industrials", "Capital Goods"),
    "capital goods": ("Industrials", "Capital Goods"),
    "capital equipment": ("Industrials", "Capital Goods"),
    "aerospace & defense": ("Industrials", "Capital Goods"),
    "aerospace and defense": ("Industrials", "Capital Goods"),
    "building products": ("Industrials", "Capital Goods"),
    "construction & engineering": ("Industrials", "Capital Goods"),
    "construction and engineering": ("Industrials", "Capital Goods"),
    "construction & building": ("Industrials", "Capital Goods"),
    "construction materials": ("Industrials", "Materials"),
    "construction": ("Industrials", "Capital Goods"),
    "electrical equipment": ("Industrials", "Capital Goods"),
    "industrial conglomerates": ("Industrials", "Capital Goods"),
    "machinery": ("Industrials", "Capital Goods"),
    "trading companies & distributors": ("Industrials", "Capital Goods"),
    "manufacturing": ("Industrials", "Capital Goods"),
    "commercial services & supplies": ("Industrials", "Commercial & Professional Services"),
    "commercial services and supplies": ("Industrials", "Commercial & Professional Services"),
    "commercial & professional services": ("Industrials", "Commercial & Professional Services"),
    "commercial and professional services": ("Industrials", "Commercial & Professional Services"),
    "commercial services": ("Industrials", "Commercial & Professional Services"),
    "professional services": ("Industrials", "Commercial & Professional Services"),
    "business services": ("Industrials", "Commercial & Professional Services"),
    "services: business": ("Industrials", "Commercial & Professional Services"),
    "human resource support services": ("Industrials", "Commercial & Professional Services"),
    "marketing services": ("Industrials", "Commercial & Professional Services"),
    "office services & supplies": ("Industrials", "Commercial & Professional Services"),
    "tax services": ("Industrials", "Commercial & Professional Services"),
    "consumer & business services": ("Industrials", "Commercial & Professional Services"),
    "environmental industries": ("Industrials", "Commercial & Professional Services"),
    "transportation": ("Industrials", "Transportation"),
    "transportation: cargo": ("Industrials", "Transportation"),
    "transportation: consumer": ("Industrials", "Transportation"),
    "transportation infrastructure": ("Industrials", "Transportation"),
    "air freight & logistics": ("Industrials", "Transportation"),
    "air freight and logistics": ("Industrials", "Transportation"),
    "logistics": ("Industrials", "Transportation"),
    "road & rail": ("Industrials", "Transportation"),
    "road and rail": ("Industrials", "Transportation"),
    "marine": ("Industrials", "Transportation"),
    "marine transportation": ("Industrials", "Transportation"),

    # ── Information Technology ──
    "information technology": ("Information Technology", "Software & Services"),
    "high tech industries": ("Information Technology", "Software & Services"),
    "software": ("Information Technology", "Software & Services"),
    "software & services": ("Information Technology", "Software & Services"),
    "software and services": ("Information Technology", "Software & Services"),
    "software (internet, mobile, hardware)": ("Information Technology", "Software & Services"),
    "application software": ("Information Technology", "Software & Services"),
    "system software": ("Information Technology", "Software & Services"),
    "internet software & services": ("Information Technology", "Software & Services"),
    "internet software and services": ("Information Technology", "Software & Services"),
    "internet services": ("Information Technology", "Software & Services"),
    "internet consumer & business services": ("Information Technology", "Software & Services"),
    "internet consumer and business services": ("Information Technology", "Software & Services"),
    "internet": ("Information Technology", "Software & Services"),
    "it services": ("Information Technology", "Software & Services"),
    "information services": ("Information Technology", "Software & Services"),
    "technology hardware, storage & peripherals": ("Information Technology", "Technology Hardware & Equipment"),
    "technology hardware, storage and peripherals": ("Information Technology", "Technology Hardware & Equipment"),
    "technology hardware": ("Information Technology", "Technology Hardware & Equipment"),
    "electronics & computer hardware": ("Information Technology", "Technology Hardware & Equipment"),
    "electronic equipment, instruments & components": ("Information Technology", "Technology Hardware & Equipment"),
    "electronic equipment, instruments and components": ("Information Technology", "Technology Hardware & Equipment"),
    "electronic equipment": ("Information Technology", "Technology Hardware & Equipment"),
    "communications equipment": ("Information Technology", "Technology Hardware & Equipment"),
    "communications": ("Information Technology", "Technology Hardware & Equipment"),
    "semiconductors & semiconductor equipment": ("Information Technology", "Semiconductors & Semiconductor Equipment"),
    "semiconductors and semiconductor equipment": ("Information Technology", "Semiconductors & Semiconductor Equipment"),
    "semiconductors": ("Information Technology", "Semiconductors & Semiconductor Equipment"),

    # ── Materials ──
    "materials": ("Materials", "Materials"),
    "chemicals": ("Materials", "Materials"),
    "metals & mining": ("Materials", "Materials"),
    "metals and mining": ("Materials", "Materials"),
    "paper & forest products": ("Materials", "Materials"),
    "paper and forest products": ("Materials", "Materials"),
    "paper & plastic packaging products & materials": ("Materials", "Materials"),
    "containers & packaging": ("Materials", "Materials"),
    "containers and packaging": ("Materials", "Materials"),
    "construction & raw materials": ("Materials", "Materials"),

    # ── Real Estate ──
    "real estate": ("Real Estate", "Real Estate"),
    "real estate management & development": ("Real Estate", "Real Estate"),
    "real estate management and development": ("Real Estate", "Real Estate"),
    "real estate mgmt. & development": ("Real Estate", "Real Estate"),
    "real estate development": ("Real Estate", "Real Estate"),
    "real estate operating companies": ("Real Estate", "Real Estate"),
    "equity real estate investment trusts (reits)": ("Real Estate", "Real Estate"),
    "real estate investment trusts (reits)": ("Real Estate", "Real Estate"),

    # ── Utilities ──
    "utilities": ("Utilities", "Utilities"),
    "electric utilities": ("Utilities", "Utilities"),
    "gas utilities": ("Utilities", "Utilities"),
    "multi-utilities": ("Utilities", "Utilities"),
    "water utilities": ("Utilities", "Utilities"),
    "independent power and renewable electricity producers": ("Utilities", "Utilities"),
    "sustainable and renewable technology": ("Utilities", "Utilities"),

    # ── BDC-specific (Black Box: fund-of-funds / JV / CLO holdings) ──
    "investment funds": ("Black Box", "JV / Fund of Funds"),
    "investment fund": ("Black Box", "JV / Fund of Funds"),
    "investment funds and vehicles": ("Black Box", "JV / Fund of Funds"),
    "investment funds & vehicles": ("Black Box", "JV / Fund of Funds"),
    "investment vehicles & other": ("Black Box", "JV / Fund of Funds"),
    "multi-sector holdings": ("Black Box", "CLO / Structured Credit"),
    "structured credit": ("Black Box", "CLO / Structured Credit"),
    "structured product": ("Black Box", "CLO / Structured Credit"),
    "structured finance": ("Black Box", "CLO / Structured Credit"),
    "asset based finance": ("Financials", "Diversified Financials"),
    "asset-based finance": ("Financials", "Diversified Financials"),
    "money market funds (included in cash and cash equivalents)":
        ("Cash & Equivalents", "Cash & Equivalents"),
    "money market funds": ("Cash & Equivalents", "Cash & Equivalents"),

    # ── Extended mappings discovered in raw data ──
    "consumer goods: non-durable": ("Consumer Staples", "Household & Personal Products"),
    "consumer goods - non-durables": ("Consumer Staples", "Household & Personal Products"),
    "wholesale": ("Industrials", "Commercial & Professional Services"),
    "wholesale distribution": ("Industrials", "Commercial & Professional Services"),
    "other investments": ("Other", "Other"),
    "auto aftermarket & services": ("Consumer Discretionary", "Automobiles & Components"),
    "auto aftermarket and services": ("Consumer Discretionary", "Automobiles & Components"),
    "education": ("Consumer Discretionary", "Consumer Services"),
    "education services": ("Consumer Discretionary", "Consumer Services"),
    "space technologies": ("Industrials", "Capital Goods"),
    "diversified support services": ("Industrials", "Commercial & Professional Services"),
    "infrastructure and environmental services":
        ("Industrials", "Commercial & Professional Services"),
    "support services": ("Industrials", "Commercial & Professional Services"),
    "equity securities": ("Other", "Other"),
    "equity investments": ("Other", "Other"),
    "debt investments": ("Other", "Other"),
    "warrant investments": ("Other", "Other"),
    "data processing & outsourced services":
        ("Information Technology", "Software & Services"),
    "diversified support": ("Industrials", "Commercial & Professional Services"),
    "specialty manufacturing": ("Industrials", "Capital Goods"),
    "manufacturing equipment": ("Industrials", "Capital Goods"),
    "leisure equipment & products": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "leisure equipment and products": ("Consumer Discretionary", "Consumer Durables & Apparel"),
    "leisure facilities & services": ("Consumer Discretionary", "Consumer Services"),
    "leisure facilities and services": ("Consumer Discretionary", "Consumer Services"),
    "automotive aftermarket": ("Consumer Discretionary", "Automobiles & Components"),
    "automotive parts and equipment": ("Consumer Discretionary", "Automobiles & Components"),
    "agriculture": ("Materials", "Materials"),
    "agricultural products": ("Consumer Staples", "Food, Beverage & Tobacco"),
    "chemicals, plastics & rubber": ("Materials", "Materials"),
    "construction materials": ("Materials", "Materials"),
    "forest products & paper": ("Materials", "Materials"),
    # OCSL / extended GICS sub-industries
    "airport services": ("Industrials", "Transportation"),
    "cable & satellite": ("Communication Services", "Media & Entertainment"),
    "alternative carriers": ("Communication Services", "Telecommunication Services"),
    "research & consulting services":
        ("Industrials", "Commercial & Professional Services"),
    "research and consulting services":
        ("Industrials", "Commercial & Professional Services"),
    "environmental & facilities services":
        ("Industrials", "Commercial & Professional Services"),
    "environmental and facilities services":
        ("Industrials", "Commercial & Professional Services"),
    "distribution": ("Industrials", "Capital Goods"),
    "personal care products": ("Consumer Staples", "Household & Personal Products"),
    "gold": ("Materials", "Materials"),
    "office products": ("Industrials", "Commercial & Professional Services"),
    "electronics": ("Information Technology", "Technology Hardware & Equipment"),
    "consumer goods: wholesale": ("Industrials", "Commercial & Professional Services"),
    "investment vehicles": ("Black Box", "JV / Fund of Funds"),
    "drug delivery": ("Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    "manufacturing technology": ("Industrials", "Capital Goods"),
    "communications & networking":
        ("Information Technology", "Software & Services"),
    "information services":
        ("Information Technology", "Software & Services"),
    "& vehicles": ("Consumer Discretionary", "Automobiles & Components"),
    "sustainable": ("Utilities", "Utilities"),
}

# Regex-based fallbacks for things that didn't match a direct lookup.
SECTOR_FALLBACK_PATTERNS: list[tuple[re.Pattern, tuple[str, str]]] = [
    (re.compile(r"\bsoftware\b", re.I),
     ("Information Technology", "Software & Services")),
    (re.compile(r"\binternet\b", re.I),
     ("Information Technology", "Software & Services")),
    (re.compile(r"\bIT\b|information technology", re.I),
     ("Information Technology", "Software & Services")),
    (re.compile(r"semiconductor", re.I),
     ("Information Technology", "Semiconductors & Semiconductor Equipment")),
    (re.compile(r"\b(?:tech|technology)\s+hardware", re.I),
     ("Information Technology", "Technology Hardware & Equipment")),
    (re.compile(r"\belectronic\b", re.I),
     ("Information Technology", "Technology Hardware & Equipment")),
    (re.compile(r"telecom|wireless", re.I),
     ("Communication Services", "Telecommunication Services")),
    (re.compile(r"\bmedia\b|entertainment|broadcasting|publishing", re.I),
     ("Communication Services", "Media & Entertainment")),
    (re.compile(r"healthcare|health\s*care|pharma|biotech|life\s+science", re.I),
     ("Health Care", "Health Care Equipment & Services")),
    (re.compile(r"\bbank", re.I), ("Financials", "Banks")),
    (re.compile(r"\binsur", re.I), ("Financials", "Insurance")),
    (re.compile(r"financ", re.I), ("Financials", "Diversified Financials")),
    (re.compile(r"real estate|REIT", re.I), ("Real Estate", "Real Estate")),
    (re.compile(r"oil|gas|energy", re.I), ("Energy", "Energy")),
    (re.compile(r"utilit", re.I), ("Utilities", "Utilities")),
    (re.compile(r"chemical|metal|mining|forest|packaging|container|material",
                re.I), ("Materials", "Materials")),
    (re.compile(r"aerospace|defense|machinery|electrical|industrial", re.I),
     ("Industrials", "Capital Goods")),
    (re.compile(r"transport|logistic|freight|airline|trucking|rail|marine",
                re.I), ("Industrials", "Transportation")),
    (re.compile(r"profession|business\s+service|commercial\s+service", re.I),
     ("Industrials", "Commercial & Professional Services")),
    (re.compile(r"automob|automot|auto\s+component", re.I),
     ("Consumer Discretionary", "Automobiles & Components")),
    (re.compile(r"hotel|restaurant|leisure|gaming|consumer\s+service", re.I),
     ("Consumer Discretionary", "Consumer Services")),
    (re.compile(r"retail", re.I), ("Consumer Discretionary", "Retailing")),
    (re.compile(r"apparel|textile|luxury", re.I),
     ("Consumer Discretionary", "Consumer Durables & Apparel")),
    (re.compile(r"beverage|food|tobacco", re.I),
     ("Consumer Staples", "Food, Beverage & Tobacco")),
    (re.compile(r"household|personal\s+product", re.I),
     ("Consumer Staples", "Household & Personal Products")),
    (re.compile(r"\bCLO\b|structured\s+(?:credit|finance|product)", re.I),
     ("Black Box", "CLO / Structured Credit")),
    (re.compile(r"investment\s+fund", re.I),
     ("Black Box", "JV / Fund of Funds")),
]


# Sub-sector qualifiers stripped before lookup. e.g.
# "Application Software (27)" → "Application Software"
_FOOTNOTE_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")
_PERCENT_SUFFIX = re.compile(r"\s*-\s*[\d.]+\s*%\s*$")
_DASH_SUFFIX = re.compile(r"\s*[-—–]\s*(?:United States|US|U\.S\.).*$", re.I)


def _clean_sector_text(raw: str) -> str:
    s = _FOOTNOTE_SUFFIX.sub("", raw).strip()
    s = _PERCENT_SUFFIX.sub("", s).strip()
    s = _DASH_SUFFIX.sub("", s).strip()
    # Strip "Equity - " / "Debt - " prefixes
    s = re.sub(r"^(?:Funded\s+|Unfunded\s+)?(?:Debt|Equity|Warrant)\s+"
               r"Investments?\s*[-–]?\s*", "", s, flags=re.I).strip()
    # HTGC parser sometimes leaves "and X" prefix from its " and " field
    # separator; drop the leading conjunction.
    s = re.sub(r"^and\s+", "", s, flags=re.I).strip()
    # Trailing "Initial Acquisition..." / "Maturity..." text bleed
    s = re.sub(
        r"\s+(?:Initial Acquisition|Maturity|Reference Rate|Interest Rate)\b.*$",
        "", s, flags=re.I).strip()
    # Drop bare "United States" / country leftovers
    if re.fullmatch(
            r"(?:United States|US|U\.S\.|Canada|Europe|UK|United Kingdom|"
            r"Bermuda|Cayman Islands|Australia|Asia)\.?",
            s, re.I):
        return ""
    # Drop "Table of contents" / page-nav leakage
    if re.fullmatch(r"table of contents", s, re.I):
        return ""
    # Drop MAIN-style fund-section headers ("Copper Trail Fund Investments",
    # "EnCap Energy Fund Investments", "Freeport Financial Funds") that
    # capture as the "sector" of positions held inside those funds. These
    # tell us nothing about the underlying company's industry. Skip if
    # the text is one of our canonical Black Box entries — those should
    # pass through to the sector map.
    canonical_keys = {
        "investment funds", "investment fund",
        "investment funds and vehicles", "investment funds & vehicles",
        "investment vehicles", "investment vehicles & other",
    }
    if s.lower() not in canonical_keys:
        if re.search(r"\bFund\s+Investments?$", s, re.I):
            return ""
        if (re.search(r"\bFunds?$", s, re.I)
                and len(s.split()) >= 3):
            # "Freeport Financial Funds", "Bain Capital Senior Loan Funds",
            # etc. Three+ words → likely fund name, not a sector label.
            return ""
    return s


def normalize_sector(raw: str) -> tuple[str, str]:
    """Map a raw sector/industry string to (gics_sector, gics_industry_group).

    Returns ("Other", "Other") if no mapping is found.
    """
    if not raw or not raw.strip():
        return ("Other", "Other")
    cleaned = _clean_sector_text(raw)
    key = cleaned.lower().strip()
    if not key:
        return ("Other", "Other")
    if key in GICS_SECTOR_MAP:
        return GICS_SECTOR_MAP[key]
    for rx, mapping in SECTOR_FALLBACK_PATTERNS:
        if rx.search(cleaned):
            return mapping
    return ("Other", "Other")


# ── Black Box entity detection ───────────────────────────────────────
#
# BDCs frequently hold investments in joint ventures, CLOs, and
# fund-of-fund vehicles where the position itself wraps a portfolio of
# many underlying investments across multiple industries. These are
# economically opaque from a single-sector lens — classify them as
# "Black Box" regardless of how the filer reports the raw sector.

_BLACK_BOX_JV_PATTERNS = (
    # Generic JV / fund-of-funds entity-name markers
    re.compile(r"\bJV(?:\s|,|$|\s+LLC|\s+L\.?L\.?C\.?)", re.I),
    re.compile(r"\bSenior Loan Program\b", re.I),
    re.compile(r"\bSenior Loan Fund\b", re.I),
    re.compile(r"\bSenior Loan Strategy\b", re.I),
    re.compile(r"\bCredit Opportunities Partners\b", re.I),
    re.compile(r"\bMiddle Market Credit Fund\b", re.I),
    re.compile(r"\bGlick JV\b", re.I),
    re.compile(r"\bSpecialty Finance Holdings?\b", re.I),
)

_BLACK_BOX_CLO_PATTERNS = (
    # CLO vintage tickers (e.g. "Ares CLO Ltd, Series 2022-63A",
    # "KKR Financial CLO Ltd"). Avoid matching "CLO Notes" type text.
    re.compile(r"\bCLO\b", re.I),  # any CLO mention in entity name
    re.compile(r"\bMulti-Sector Holdings?\b", re.I),
    re.compile(r"\bMaster Note Business Trust\b", re.I),
    re.compile(r"\bMagnetite\s+[XIVL]+\b", re.I),  # BlackRock CLO series
    re.compile(r"\bApidos\s+(?:CLO\s+)?[XIVL]+\b", re.I),  # Apidos CLO series
    re.compile(r"\bSound Point CLO\b", re.I),
    re.compile(r"\bCredit Funding Ltd\b", re.I),
    re.compile(r"\bCatawba River\b", re.I),
    re.compile(r"\bStructured - (?:Junior|Senior|Mezz)", re.I),
    re.compile(r"\bSeries\s+\d{4}-\d", re.I),  # CLO series tickers
)


def is_black_box_entity(entity: str) -> Optional[str]:
    """Return "JV / Fund of Funds" or "CLO / Structured Credit" if the
    entity name matches a known black-box pattern. Returns None otherwise.

    Use this as an override before/after `normalize_sector` to flag
    positions where a single GICS sector is misleading."""
    if not entity:
        return None
    for rx in _BLACK_BOX_JV_PATTERNS:
        if rx.search(entity):
            return "JV / Fund of Funds"
    for rx in _BLACK_BOX_CLO_PATTERNS:
        if rx.search(entity):
            return "CLO / Structured Credit"
    return None


# Keyword → (sector, industry_group) — applied to free-text business
# descriptions (e.g. MAIN's "Roaster, Mixer and Packager of Bulk Nuts and
# Seeds"). Order matters: longer / more specific patterns first. Each entry
# is checked as a case-insensitive substring or regex against the full
# description; the first hit wins.
_DESC_KEYWORD_RULES: tuple[tuple[re.Pattern, str, str], ...] = (
    # Software & IT
    (re.compile(r"\b(software|SaaS|cloud|cyber|cybersec|IT services|tech(?:nology)? (?:services|consult|solut|platform)|digital (?:platform|marketing|product|photo)|data (?:platform|analytics)|app(?:lication)? (?:dev|platform)|web (?:platform|services))\b", re.I), "Information Technology", "Software & Services"),
    (re.compile(r"\b(semiconductor|chip(?:set)?|silicon)\b", re.I), "Information Technology", "Semiconductors & Semiconductor Equipment"),
    (re.compile(r"\b(hardware|electronic equipment|networking equipment|computer hardware|server)\b", re.I), "Information Technology", "Technology Hardware & Equipment"),
    # Healthcare
    (re.compile(r"\b(pharma(?:ceutical)?|biotech(?:nology)?|drug (?:dev|develop|manufactur)|life sciences?)\b", re.I), "Health Care", "Pharmaceuticals, Biotechnology & Life Sciences"),
    (re.compile(r"\b(hospital|clinic|medical (?:device|equipment|practice|service)|dental|veterinary|nursing|home health|hospice|behavioral health|orthop[ae]dic|dermatolog|optometr|cardiolog|oncolog|radiolog|surgery|surgical|physician|patient|health[- ]care (?:staff|service|provider|facility|technolog|equipment|suppl)|substance abuse|applied behavior analysis|ABA therapy)\b", re.I), "Health Care", "Health Care Equipment & Services"),
    # Finance
    (re.compile(r"\b(insurance (?:broker|agency|services|carrier)|reinsurance|underwriter|insurer|insurance$)\b", re.I), "Financials", "Insurance"),
    (re.compile(r"\b(bank|banking|lender|lending|credit (?:provider|services|union)|fintech|payment processor|asset manager|wealth (?:manag|advis)|investment (?:bank|advisor|manag|partnership)|specialty consumer finance|loan servicer|consumer finance|business development comp|broker[- ]dealer)\b", re.I), "Financials", "Diversified Financials"),
    # Real estate
    (re.compile(r"\b(real estate (?:invest|trust|develop|mgmt|owner|operator|brokerage)|REIT|property (?:mgmt|develop|manag)|construction)\b", re.I), "Real Estate", "Real Estate"),
    # Energy
    (re.compile(r"\b(oil (?:and|&) gas|upstream|midstream|downstream|petroleum|refining|oilfield|fracking|drilling (?:services)?|coal|natural gas|liquefied natural gas|LNG)\b", re.I), "Energy", "Energy"),
    (re.compile(r"\b(utility|utilities|power (?:gen|util|station)|electric (?:util|company)|water util|gas util|solar (?:power|gen|farm)|wind (?:power|gen|farm)|renewable energy)\b", re.I), "Utilities", "Utilities"),
    (re.compile(r"\b(backup power generation|nuclear power)\b", re.I), "Utilities", "Utilities"),
    # Materials / Industrials
    (re.compile(r"\b(chemical|specialty chemical|polymer|plastic (?:resin|compound)|metal-based laminat|metals? (?:and|&) mining|forest product|paper (?:product|mill)|packaging|container (?:and|&) packaging)\b", re.I), "Materials", "Materials"),
    (re.compile(r"\b(aerospace|defense|airline|aircraft|aviation|military)\b", re.I), "Industrials", "Capital Goods"),
    (re.compile(r"\b(machinery|industrial equipment|industrial manufact|construction equipment|heavy equipment|electrical equipment|building products?|industrial automation)\b", re.I), "Industrials", "Capital Goods"),
    (re.compile(r"\b(manufactur|production facility|fabricat|assembly|tool & die|metalwork|precision metal|die cut|electrical distribution|disconnect switch|industrial piping|specialty fabricat|component (?:manufactur|machining)|engineered (?:component|product|solution))\b", re.I), "Industrials", "Capital Goods"),
    # Transportation
    (re.compile(r"\b(trucking|freight|logistics|shipping|rail(?:road|way)?|marine transport|tanker|ocean carrier|airfreight|air freight|courier|last[- ]mile delivery|transport(?:ation)? infrastructure|port operator|tugboat|marine tourism)\b", re.I), "Industrials", "Transportation"),
    # Commercial / Professional Services
    (re.compile(r"\b(staffing (?:agency|service|firm)|talent advisory|professional service|consulting|HR services|recruitment|outsourcing|business process outsourcing|BPO|facility manag|facility (?:service|maintenance)|janitorial|landscaping|pest control|security service|environmental service|waste manag|recycling|advertising|marketing services|PR firm|public relations|legal service|accounting|audit firm|maintenance services?|snow removal|ice management|test(?:ing)?, inspection)\b", re.I), "Industrials", "Commercial & Professional Services"),
    (re.compile(r"\b(vegetation management|residential re-roofing|nuclear power staffing|healthcare temporary staffing|tech-enabled distribution)\b", re.I), "Industrials", "Commercial & Professional Services"),
    # Consumer
    (re.compile(r"\b(automotive (?:parts|aftermarket|dealer|service)|auto (?:parts|repair|service)|car (?:wash|dealer)|tire (?:retail|distrib)|vehicle (?:parts|service))\b", re.I), "Consumer Discretionary", "Automobiles & Components"),
    (re.compile(r"\b(hotel|resort|gaming|casino|cruise|leisure|restaurants?|franchisee|fast food|quick service|QSR|food service|catering|amusement park|theme park|tourism|travel agen|casual dining|fine dining)\b", re.I), "Consumer Discretionary", "Consumer Services"),
    (re.compile(r"\b(higher education|education service|child[- ]care|day[- ]care|tutoring|test prep|for-profit (?:thrift |)retail|specialty (?:apparel|footwear|jewel)|substance abuse|behavioral health|applied behavior analysis|outsourced consumer service)\b", re.I), "Consumer Discretionary", "Consumer Services"),
    (re.compile(r"\b(retailer|retail (?:chain|store|operator)|e-commerce|online retailer|department store|specialty retail|big[- ]box|wholesaler|wholesale (?:distrib|trader)|closeout|off[- ]price)\b", re.I), "Consumer Discretionary", "Retailing"),
    (re.compile(r"\b(apparel|textile|footwear|sporting goods|luxury goods|household appliances|home furnish|furniture|consumer plastic product|beaded ice cream|toy (?:maker|manufact)|musical instrument)\b", re.I), "Consumer Discretionary", "Consumer Durables & Apparel"),
    (re.compile(r"\b(supermarket|grocery|food retailer|food distributor|specialized food|beverage (?:distrib|maker|producer|solutions)|food processor|nut(?:rition)? (?:supplement|product)|rice processor|food (?:and|&) staples|coffee (?:roaster|company)|ice cream|premium beaded|roaster|baker|nuts and seeds|food ingredient|food and beverage|specialty food|tea|wine|spirit|brewer)\b", re.I), "Consumer Staples", "Food, Beverage & Tobacco"),
    (re.compile(r"\b(household products|personal product|personal care|cosmetic|consumer packaged goods|CPG|consumer health)\b", re.I), "Consumer Staples", "Household & Personal Products"),
    # Media / Communications
    (re.compile(r"\b(media (?:company|operator)|broadcast|newspaper operator|local newspaper|cable network|publishing|content creator|advertis(?:ing agency|ing network)|film studio|music label|streaming service|gaming studio|video game)\b", re.I), "Communication Services", "Media & Entertainment"),
    (re.compile(r"\b(telecom(?:munication)?|wireless carrier|wireline|broadband (?:provider|carrier)|ISP|internet service|cable (?:provider|operator))\b", re.I), "Communication Services", "Telecommunication Services"),
    # CLO / structured credit
    (re.compile(r"\b(CLO|collateralized loan obligation|structured credit|securitization)\b", re.I), "Black Box", "CLO / Structured Credit"),
    # JV / fund of funds
    (re.compile(r"\b(joint venture|fund of funds|investment partnership)\b", re.I), "Black Box", "JV / Fund of Funds"),
)


def classify_from_description(desc: str) -> Optional[tuple[str, str]]:
    """Keyword-based sector classifier for free-text business descriptions
    (used by MAIN and others whose SOI HTML carries only a description, no
    sector field). Returns (sector, industry_group) on a confident hit,
    None otherwise (caller falls back to Other)."""
    if not desc:
        return None
    for rx, g, ig in _DESC_KEYWORD_RULES:
        if rx.search(desc):
            return (g, ig)
    return None


def classify_position(entity: str, raw_sector_xbrl: str,
                      raw_sector_soi: str,
                      business_description: str = "") -> tuple[str, str]:
    """Top-level classifier: combines entity-based black-box detection
    with raw-sector normalization, falling back to business-description
    keyword classification when sector fields are unusable.

    Order of resolution:
      1. If entity matches a Black Box pattern → ("Black Box", sub)
      2. Try normalize_sector on XBRL raw value
      3. Try normalize_sector on SOI HTML raw value
      4. Keyword-classify the free-text business description
      5. Return ("Other", "Other")
    """
    bb = is_black_box_entity(entity or "")
    if bb:
        return ("Black Box", bb)
    if raw_sector_xbrl:
        g, ig = normalize_sector(raw_sector_xbrl)
        if g != "Other":
            return (g, ig)
    if raw_sector_soi:
        g, ig = normalize_sector(raw_sector_soi)
        if g != "Other":
            return (g, ig)
    by_desc = classify_from_description(business_description)
    if by_desc is not None:
        return by_desc
    return ("Other", "Other")
