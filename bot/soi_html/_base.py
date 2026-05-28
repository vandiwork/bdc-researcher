"""Base SOI HTML parser.

Implements a generic column-position-grid table walker used by most
BDC parsers. ARCC, BXSL, CGBD, GSBD, MAIN, MSDL, NMFC, OCSL and
others all use roughly the same structural pattern:

  - SOI is paginated across many <table> elements (each visual page)
  - Each table repeats the header row
  - Money columns split into ($-sign / value / padding) cells
  - Sector breaks appear as full-width single-text rows

Subclasses provide:
  - `ticker` (required)
  - `column_aliases` — extra header-label → field mappings beyond defaults
  - `known_sectors` — optional set of recognized sector strings
  - `find_soi_region(text) → (region_start, region_end)` — optional override
  - `header_anchor` — regex string to locate the first SOI header row
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from lxml import html as lhtml


# ── ParsedRow output schema ───────────────────────────────────────────

@dataclass
class ParsedRow:
    bdc: str = ""
    issuer: str = ""
    sector: Optional[str] = None
    affiliation: Optional[str] = None   # Unaffiliated / Affiliated / Controlled
    business_description: Optional[str] = None
    investment_type: Optional[str] = None
    base_rate: Optional[str] = None
    spread: Optional[float] = None
    interest_rate: Optional[float] = None
    pik_rate: Optional[float] = None
    rate_floor: Optional[float] = None
    acquisition_date: Optional[str] = None
    maturity_date: Optional[str] = None
    shares_units: Optional[float] = None
    principal: Optional[float] = None
    cost: Optional[float] = None
    fair_value: Optional[float] = None
    pct_net_assets: Optional[float] = None
    footnotes: Optional[str] = None
    row_kind: str = "POSITION"


# ── Standard header label → field name mapping ────────────────────────

DEFAULT_HEADER_MAP = {
    # "Company"-style headers — these UNAMBIGUOUSLY identify the issuer column
    "Company": "company",
    "Portfolio Company": "company",
    "Issuer": "company",
    "Industry/Company": "company",
    "Portfolio Company, Location and Industry": "company",
    # "Investment"-style headers may be EITHER the company column (BXSL,
    # GSBD, MSDL) OR the type column (ARCC, OBDC, PSEC, TSLX) depending
    # on the filer. By default treat as TYPE; the BDCs where it's the
    # company column override via column_aliases.
    "Industry": "industry",
    "Business Description": "description",
    "Investment": "investment_type",
    "Investments": "investment_type",
    "Investment Type": "investment_type",
    "Type of Investment": "investment_type",
    "Instrument": "investment_type",
    "Coupon": "coupon",
    "Coupon/Yield": "coupon",
    "Interest Rate": "coupon",
    "Interest Rate and Floor": "coupon",
    "Cash Interest Rate": "coupon",
    "Interest": "coupon",
    "Total Coupon": "coupon",
    "Rate": "coupon",
    "Total Rate": "coupon",
    "Reference": "reference",
    "Reference Rate": "reference",
    "Reference Rate and Spread": "reference",
    "Ref. Rate": "reference",
    "Ref": "reference",
    "Index": "reference",
    "Spread": "spread",
    "Spread Above Index": "spread",
    "Floor": "floor",
    "Cash": "cash_rate",
    "PIK": "pik_rate",
    "PIK Rate": "pik_rate",
    "Acquisition Date": "acq",
    "Acq. Date": "acq",
    "Initial Acquisition Date": "acq",
    "Investment Date": "acq",
    "Maturity Date": "maturity",
    "Maturity": "maturity",
    "Maturity/Expiration Date": "maturity",
    "Legal Maturity": "maturity",
    "Expiration": "maturity",
    "Shares/Units": "shares",
    "Shares": "shares",
    "Par/Units": "shares",
    "Par/Shares": "shares",
    "Par Amount/Units": "shares",
    "Par Amount/ Shares": "shares",
    "Principal/Shares": "shares",
    "Principal Amount, Par Value or Shares": "shares",
    "Principal/Par/Shares": "shares",
    "Principal ($) / Shares": "shares",
    "Principal Amount/Par Value or Shares": "shares",
    "Principal/Shares (3)": "shares",
    "Principal/Shares (2)": "shares",
    "Principal": "principal",
    "Principal Amount": "principal",
    "Principal Value": "principal",
    "Par Amount": "principal",
    "Par/Principal Amount": "principal",
    "Par / Units": "principal",
    "Cost": "cost",
    "Amortized Cost": "cost",
    "Fair Value": "fair_value",
    "Value": "fair_value",
    "Market Value": "fair_value",
    "% of Net Assets": "pct_nav",
    "Percent of Net Assets": "pct_nav",
    "Percentage of Net Assets": "pct_nav",
    "% of NAV": "pct_nav",
    "% of Total Cash and Investments": "pct_nav",
    "Footnotes": "footnotes",
    "Notes": "footnotes",
}


# ── Parsing helpers ───────────────────────────────────────────────────

_RATE_RE = re.compile(r"([0-9]+\.[0-9]+)\s*%")
_PIK_RE = re.compile(r"\(\s*([0-9]+\.[0-9]+)\s*%\s*PIK\s*\)", re.I)
_BASE_RX = re.compile(
    r"\b(SOFR|SONIA|EURIBOR|CDOR|TIBOR|BBSY|STIBOR|NIBOR|CIBOR|"
    r"BKBM|Prime|LIBOR|BSBY)\b", re.I)
# Single-letter abbreviations some filers use (GSBD/MSDL/OBDC: "S + 4.75 %"
# or sometimes just "S+" with the rate in a separate cell)
_BASE_ABBREV = {"S": "SOFR", "E": "EURIBOR", "B": "BBSY",
                "P": "Prime", "L": "LIBOR"}
_BASE_ABBREV_RX = re.compile(
    r"(?:^|\s)([SEBPL])\s*\+\s*(?:\d|$)", re.I)
_DATE_MMYYYY = re.compile(r"^(\d{1,2})/(\d{4})$")
_DATE_MMDDYYYY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DATE_MMDDYY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$")
_DATE_MMYY = re.compile(r"^(\d{1,2})/(\d{2})$")
_FOOTNOTE_TAIL = re.compile(r"\s*\([0-9, ]+\)\s*$")


def to_float(s: Optional[str]) -> Optional[float]:
    """Parse '$ 13.2', '13,200', '(13.2)', '8.74 %' etc. Parens = negative."""
    if not s:
        return None
    t = s.strip()
    if not t or t in ("$", "—", "-", "&mdash;"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = (t.strip("()")
         .replace("$", "")
         .replace(",", "")
         .replace("%", "")
         .strip())
    if not t:
        return None
    try:
        v = float(t)
        return -v if neg else v
    except ValueError:
        return None


def parse_rate(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = _RATE_RE.search(s)
    return float(m.group(1)) if m else None


def parse_pik_rate(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = _PIK_RE.search(s)
    return float(m.group(1)) if m else None


def parse_base_rate(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = _BASE_RX.search(s)
    if m:
        return m.group(1).upper()
    m = _BASE_ABBREV_RX.search(s)
    if m:
        return _BASE_ABBREV.get(m.group(1).upper(), m.group(1).upper())
    return None


def parse_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    t = s.strip()
    m = _DATE_MMDDYYYY.match(t)
    if m:
        mo, dy, yr = m.groups()
        return f"{yr}-{int(mo):02d}-{int(dy):02d}"
    m = _DATE_MMYYYY.match(t)
    if m:
        mo, yr = m.groups()
        return f"{yr}-{int(mo):02d}"
    # 2-digit year (GSBD, MSDL): "06/17/26" → 2026-06-17
    # Assume years 00-50 → 2000-2050, years 51-99 → 1951-1999
    m = _DATE_MMDDYY.match(t)
    if m:
        mo, dy, yr = m.groups()
        yr_full = int(yr)
        century = 2000 if yr_full <= 50 else 1900
        return f"{century + yr_full}-{int(mo):02d}-{int(dy):02d}"
    # MM/YY (BBDC): "04/22" → 2022-04
    m = _DATE_MMYY.match(t)
    if m:
        mo, yr = m.groups()
        yr_full = int(yr)
        century = 2000 if yr_full <= 50 else 1900
        return f"{century + yr_full}-{int(mo):02d}"
    return None


def looks_like_money(s: str) -> bool:
    if not s:
        return False
    t = s.replace("$", "").replace(",", "").strip("()% ")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


# ── Row / column extraction ───────────────────────────────────────────

def row_cells_with_cols(row) -> list[tuple[int, int, str]]:
    """For each <td>/<th>, return (col_start, colspan, text)."""
    out: list[tuple[int, int, str]] = []
    col = 0
    for c in row.xpath("./td|./th"):
        colspan = int(c.get("colspan", 1) or 1)
        t = " ".join(s.strip() for s in c.xpath(".//text()") if s.strip())
        out.append((col, colspan, t))
        col += colspan
    return out


def build_header_map(
    row, extra_aliases: Optional[dict[str, str]] = None
) -> dict[int, tuple[int, str]]:
    """Find header cells and return {col_start: (col_end_exclusive, field)}."""
    aliases = dict(DEFAULT_HEADER_MAP)
    if extra_aliases:
        aliases.update(extra_aliases)
    # Normalize aliases by collapsing whitespace
    norm_aliases = {_norm_ws(k): v for k, v in aliases.items()}
    fields: dict[int, tuple[int, str]] = {}
    for col_start, colspan, text in row_cells_with_cols(row):
        if not text:
            continue
        clean = _FOOTNOTE_TAIL.sub("", text).strip()
        for variant in (
            clean,
            _norm_ws(clean),
            re.sub(r"\s*\([^)]*\)", "", clean).strip(),
            _norm_ws(re.sub(r"\s*\([^)]*\)", "", clean).strip()),
            text.strip(),
            _norm_ws(text.strip()),
        ):
            if variant in aliases:
                fields[col_start] = (col_start + colspan, aliases[variant])
                break
            if variant in norm_aliases:
                fields[col_start] = (col_start + colspan, norm_aliases[variant])
                break
    return fields


def _norm_ws(s: str) -> str:
    """Collapse all whitespace (incl. NBSP) to single spaces."""
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


_AFFIL_PATTERNS = (
    (re.compile(r"non[- ]controlled\s*/\s*non[- ]affiliat", re.I), "Unaffiliated"),
    (re.compile(r"\bnon[- ]affiliat", re.I), "Unaffiliated"),
    (re.compile(r"non[- ]controlled\s*[/ ]\s*affiliated", re.I), "Affiliated Non-Controlled"),
    (re.compile(r"\baffiliated\s+issuer\s+non[- ]controlled", re.I), "Affiliated Non-Controlled"),
    (re.compile(r"\baffiliat(ed|e)\s+(?:issuer\s+)?(?:non[- ]controlled|investments?)", re.I), "Affiliated"),
    (re.compile(r"\bcontrolled\s+affiliat", re.I), "Affiliated Controlled"),
    (re.compile(r"\baffiliated\s+issuer\s+controlled", re.I), "Affiliated Controlled"),
    (re.compile(r"\bcontrol(?:led)?\s+investments?\b", re.I), "Affiliated Controlled"),
    (re.compile(r"\bmajority[- ]owned\s+investments?\b", re.I), "Affiliated Controlled"),
)


def _parse_affiliation_header(text: str) -> Optional[str]:
    """Detect 'Non-controlled/Non-Affiliated Investments' style section
    headers and return a normalized affiliation tag."""
    if not text:
        return None
    if "investments" not in text.lower() and "issuer" not in text.lower():
        return None
    for rx, label in _AFFIL_PATTERNS:
        if rx.search(text):
            return label
    return None


# Investment-type section headers. BDCs like BXSL and FSK structure
# their SOI so the type appears only as a section break (e.g.
# "First Lien Debt Investments - 84.5%" or just "First Lien Debt"),
# not per-row. We track these. Match LONGER patterns first so
# "First Lien Debt" doesn't accidentally beat "First Lien Note" etc.
_INV_TYPE_HEADER_PATTERNS = (
    # Equity / fund flavors (more specific phrases first)
    (re.compile(r"^preferred\s+(?:stock|equity|units?|shares?)", re.I),
     "Preferred Equity"),
    (re.compile(r"^common\s+(?:stock|equity|units?|shares?)", re.I),
     "Common Equity"),
    (re.compile(r"^equity\s+investments?\b", re.I), "Common Equity"),
    (re.compile(r"^warrant\s+investments?\b", re.I), "Warrant"),
    (re.compile(r"^warrants?\b", re.I), "Warrant"),
    # Structured credit
    (re.compile(r"^structured\b.*\b(?:credit|note|investment|finance)",
                re.I), "Structured Credit"),
    (re.compile(r"^CLO\b", re.I), "Structured Credit"),
    # Lien-based debt — allow short form ("First Lien Debt") or full
    # ("First Lien Debt Investments - 84.5%").
    (re.compile(r"^first\s+lien\b.*\b(?:debt|loan|note|investment)", re.I),
     "First Lien"),
    (re.compile(r"^1st\s+lien\b.*\b(?:debt|loan|note|investment)", re.I),
     "First Lien"),
    (re.compile(r"^second\s+lien\b.*\b(?:debt|loan|note|investment)", re.I),
     "Second Lien"),
    (re.compile(r"^2nd\s+lien\b.*\b(?:debt|loan|note|investment)", re.I),
     "Second Lien"),
    (re.compile(r"^senior\s+secured\b.*\b(?:debt|loan|note|investment)",
                re.I), "First Lien"),
    (re.compile(r"^senior\s+subordinated\b", re.I), "Subordinated"),
    (re.compile(r"^subordinated\b.*\b(?:debt|loan|note|investment)", re.I),
     "Subordinated"),
    (re.compile(r"^mezzanine\b", re.I), "Mezzanine"),
    (re.compile(r"^unitranche\b", re.I), "First Lien"),
    (re.compile(r"^one[\s\-]?stop\b", re.I), "First Lien"),
    (re.compile(r"^unsecured\b.*\b(?:debt|loan|note|investment)", re.I),
     "Unsecured"),
    # Generic "Debt Investments" (no lien specified) → assume first lien
    (re.compile(r"^(?:funded|unfunded)\s+debt\s+investment", re.I),
     "First Lien"),
    (re.compile(r"^debt\s+investments?\b", re.I), "First Lien"),
    # Bare forms (no qualifier) — match last
    (re.compile(r"^first\s+lien\b", re.I), "First Lien"),
    (re.compile(r"^second\s+lien\b", re.I), "Second Lien"),
    (re.compile(r"^senior\s+secured\b", re.I), "First Lien"),
)


def _parse_investment_type_header(text: str) -> Optional[str]:
    """Detect investment-type section header rows (BXSL, FSK style) and
    return a canonical type label. Returns None if not a type header.

    We strip trailing affiliation qualifiers ("- non-controlled/...") and
    "(continued)" before matching."""
    if not text:
        return None
    s = text.strip()
    # Strip trailing affiliation tail and "(continued)"
    s = re.sub(r"\s*[—\-–]\s*non[- ]controlled.*$", "", s, flags=re.I).strip()
    s = re.sub(r"\s*\((?:continued|cont\.?)\)\s*$", "", s, flags=re.I).strip()
    s = re.sub(r"\s*[—\-–]\s*\d+\.\d+\s*%.*$", "", s).strip()
    s = s.rstrip(".")
    for rx, label in _INV_TYPE_HEADER_PATTERNS:
        if rx.match(s):
            return label
    return None


# Tranche-descriptor patterns that appear in the company column on
# continuation rows of a multi-tranche position. When matched, treat
# as a continuation (inherit current_issuer), not as a new issuer.
_TRANCHE_DESCRIPTOR_RX = re.compile(
    r"^(?:First Lien|Second Lien|Senior Subordinated|Subordinated|"
    r"Unitranche|Mezzanine|Preferred|Common|Series [A-Z0-9]|Class [A-Z0-9]|"
    r"Term Loan|Revolver|Delayed Draw|Bridge Loan|Warrant|"
    r"Member Units?|LLC Units?|LP Units?|Limited Partner|Partnership|"
    r"Membership|Participation|Equity Interest|Convertible|"
    r"Trust Certificates?|Structured Note|"
    r"Incremental|Senior Secured|Unsecured Note|Senior Note|"
    r"Junior Note|Senior Loan|Secured Note|Acquisition Loan|"
    r"Super Priority|First Out|Second Out|Third Out|"
    r"Revolving Credit Facility|Letter of Credit|"
    r"Royalty|Limited Liability|Membership Interest|"
    r"Equipment Note|Mortgage Loan|Real Estate Loan|"
    r"PIK|Cash plus|Floating|Fixed Rate)\b", re.I)


def _looks_like_tranche_descriptor(text: str) -> bool:
    """True if text appears to be a tranche description rather than
    an issuer name (e.g. 'First Lien Term Loan A to Spartan Energy Services')."""
    return bool(_TRANCHE_DESCRIPTOR_RX.match(text))


_COMPANY_SUFFIX_RX = re.compile(
    r"(?:,?\s+(?:Inc|LLC|L\.?P\.?|Ltd|Corp|Corporation|Holdings|HoldCo|"
    r"TopCo|MidCo|BidCo|S\.?A\.?R\.?L\.?|GmbH|B\.?V\.?|ULC|N\.?V\.?|"
    r"Limited|Group|Company|Co))\.?(?:\s*\([^)]*\))?\s*$", re.I)
# Also detect company names that don't end in a corporate suffix but
# contain one (e.g., "Acme Inc. (f/k/a Old Name)")
_COMPANY_SUFFIX_ANYWHERE_RX = re.compile(
    r"\b(?:Inc|LLC|L\.?P\.?|Corp|Corporation|HoldCo|TopCo|MidCo|BidCo|"
    r"GmbH|S\.?A\.?R\.?L\.?|B\.?V\.?|ULC|N\.?V\.?)\.?\b", re.I)


def _looks_like_company_name(text: str) -> bool:
    """Detect text that looks like a company/issuer name rather than
    a sector. Sectors don't typically contain corporate suffixes."""
    if not text:
        return False
    # Strip trailing footnote markers (*, **, †, ‡, digits in parens, etc.)
    # so "NMFC Senior Loan Program IV LLC**" still matches as a company.
    stripped = re.sub(r"[\s\*†‡]+$", "", text).strip()
    stripped = re.sub(r"\s*\(\d+\)\s*$", "", stripped).strip()
    if _COMPANY_SUFFIX_RX.search(stripped):
        return True
    # If it contains corp suffix anywhere AND has a comma, treat as company
    if "," in stripped and _COMPANY_SUFFIX_ANYWHERE_RX.search(stripped):
        return True
    # If it contains "(f/k/a", "(d/b/a", "(dba", "(fka" — common alias markers
    if re.search(r"\((?:f/k/a|d/b/a|dba|fka|aka)\b", stripped, re.I):
        return True
    return False


def _looks_like_industry_name(text: str) -> bool:
    """Detect text that looks like a GICS industry/sub-industry name.

    Used to distinguish NMFC's industry-row pattern (where the industry
    appears as a standalone row between issuer and type rows) from a
    new issuer name. Returns True iff:
      - text is short (<= 60 chars, <= 6 words)
      - does not look like a company name
      - has an EXACT match in the GICS sector map (not just a regex
        fallback). This prevents company names that happen to contain
        industry keywords like "Energy Services" or "Financial Group"
        from being treated as sector labels.
    """
    if not text or len(text) > 60:
        return False
    if len(text.split()) > 6:
        return False
    if _looks_like_company_name(text):
        return False
    try:
        from normalize import GICS_SECTOR_MAP, _clean_sector_text  # type: ignore
    except ImportError:
        return False
    cleaned = _clean_sector_text(text)
    return cleaned.lower().strip() in GICS_SECTOR_MAP


def assign_cells_to_fields(
    cells: list[tuple[int, int, str]],
    header_map: dict[int, tuple[int, str]],
) -> dict[str, str]:
    """Given body cells and a header map, return {field: text}."""
    by_field: dict[str, list[str]] = {}
    ranges = sorted(header_map.items())
    for col_start, colspan, text in cells:
        if not text:
            continue
        cell_end = col_start + colspan
        for hcol_start, (hcol_end, field) in ranges:
            if col_start < hcol_end and cell_end > hcol_start:
                by_field.setdefault(field, []).append(text)
                break
    return {field: " ".join(parts) for field, parts in by_field.items()}


def extract_money(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    t = s.replace("$", "").strip()
    if t in ("", "—", "-"):
        return None
    return to_float(t)


# ── Base parser class ─────────────────────────────────────────────────

class SoiHtmlParser:
    """Generic SOI HTML parser. Subclass for each BDC."""

    ticker: str = ""

    # Regex to locate the FIRST SOI header row anchor (e.g. r"Company \(1\)")
    header_anchor: str = r"Company"

    # Additional header-label → field aliases beyond defaults
    column_aliases: dict[str, str] = {}

    # Inject a column at a fixed (col_start, col_end_exclusive) when the
    # filer's HTML has no header label there (e.g. GBDC's issuer-name
    # column at col[3-6] which is unlabeled). Merged into header_map.
    extra_columns: dict[tuple[int, int], str] = {}

    # Sector strings to look for in prose between tables (subclass override)
    known_sectors: tuple[str, ...] = ()

    # End-of-SOI markers (any match closes the region)
    soi_end_markers: tuple[str, ...] = (
        "Total investments, at fair value",
        "Total investments at fair value",
        "Total Investments",
        "TOTAL INVESTMENTS",
        "Total portfolio investments",
    )

    # Filer's SOI value scale. Most BDCs report in $M directly in the
    # SOI table; some (BCSF, HTGC, MAIN, MFIC) report in $K (i.e. raw
    # 5,124 means $5.124M). Set to 0.001 for $K filers to convert to $M.
    value_scale_m: float = 1.0

    def parse_soi(self, html_bytes: bytes) -> list[ParsedRow]:
        text = html_bytes.decode("utf-8", errors="replace")

        # Try every match of the header anchor; accept the first one whose
        # enclosing <table> contains a valid header row mapping. This
        # avoids landing on a narrative occurrence of "Portfolio Company"
        # before the actual SOI table.
        anchor_re = re.compile(self.header_anchor)
        anchor_positions = [m.start() for m in anchor_re.finditer(text)]
        if not anchor_positions:
            return []

        header_map: dict[int, tuple[int, str]] = {}
        tbl_start = -1
        for pos in anchor_positions:
            ts = text.rfind("<table", 0, pos)
            te = text.find("</table>", pos)
            if ts < 0 or te < 0:
                continue
            first_html = text[ts:te + len("</table>")]
            try:
                first_doc = lhtml.fromstring(first_html)
            except Exception:
                continue
            # Some filers split headers across 2-6 consecutive rows. Merge
            # all header rows we encounter until we hit a non-header row OR
            # we've consumed enough rows.
            merged_hm: dict[int, tuple[int, str]] = {}
            rows_consumed = 0
            consecutive_non_header = 0
            for row in first_doc.xpath("//tr"):
                hm = build_header_map(row, self.column_aliases)
                if not hm:
                    consecutive_non_header += 1
                    if consecutive_non_header >= 2 and merged_hm:
                        break
                    continue
                consecutive_non_header = 0
                merged_hm.update(hm)
                rows_consumed += 1
                if rows_consumed >= 6:
                    break
            # Inject filer-specific extra column overrides (e.g. GBDC's
            # unlabeled issuer column at col[3-6]).
            for (col_s, col_e), field in self.extra_columns.items():
                merged_hm[col_s] = (col_e, field)
            fields = {f for _, (_, f) in merged_hm.items()}
            if "company" in fields and fields & {"fair_value", "cost", "principal"}:
                header_map = merged_hm
                tbl_start = ts
                break
        if not header_map or tbl_start < 0:
            return []

        # If no fair_value column was found but we have cost, use cost as proxy
        # (some filers like GSBD don't have a Fair Value column for the
        # restricted-securities sub-table). The position emit guard checks
        # `fair_value` so swap field name if needed.
        has_fv_col = any(f == "fair_value" for _, (_, f) in header_map.items())
        if not has_fv_col:
            # Promote the last "cost" or "value"-style column to fair_value
            for k in sorted(header_map.keys(), reverse=True):
                end, f = header_map[k]
                if f in ("cost", "value"):
                    header_map[k] = (end, "fair_value")
                    break

        # Determine SOI region end
        region_end = len(text)
        for marker in self.soi_end_markers:
            p = text.find(marker, tbl_start)
            if 0 < p < region_end:
                region_end = p

        # tbl_end is needed once for the first chunk; we'll iterate all
        # tables from tbl_start onward.
        tbl_end = text.find("</table>", tbl_start)

        # Walk every <table> in the SOI region
        table_starts = [
            tbl_start + ts.start()
            for ts in re.finditer(r"<table[^>]*>", text[tbl_start:region_end])
        ]
        max_col = max(end for _, (end, _) in header_map.items())

        positions: list[ParsedRow] = []
        current_sector: Optional[str] = None
        current_affil: Optional[str] = None
        current_issuer: Optional[str] = None
        current_description: Optional[str] = None
        current_inv_type: Optional[str] = None
        has_industry_col = any(
            f == "industry" for _, (_, f) in header_map.items())
        has_investment_type_col = any(
            f == "investment_type" for _, (_, f) in header_map.items())

        for ti, ts in enumerate(table_starts):
            te = text.find("</table>", ts)
            if te < 0 or te > region_end:
                break

            # Look for sector in prose between tables
            if ti > 0:
                between = text[table_starts[ti - 1]:ts]
                sec = self._find_sector_in_prose(between)
                if sec:
                    current_sector = sec

            try:
                doc = lhtml.fromstring(text[ts:te + len("</table>")])
            except Exception:
                continue

            for row in doc.xpath("//tr"):
                cells = row_cells_with_cols(row)
                if not cells:
                    continue
                non_empty = [(s, n, t) for s, n, t in cells if t]
                if not non_empty:
                    continue

                # Skip repeating header rows
                first_text = non_empty[0][2]
                if any(label in first_text for label in
                       ("Company", "Portfolio Company", "Issuer",
                        "Investments", "Investment Type")):
                    if len(non_empty) >= 4:
                        continue

                # Section-break detection — fires for BOTH:
                #   (a) BDCs without an Industry column (e.g. ARCC) where
                #       sectors live entirely in section rows, and
                #   (b) BDCs WITH an Industry column (e.g. GSBD, MSDL) that
                #       *also* use section-break rows for affiliation /
                #       region / tranche-type breakouts.
                # For (b), we don't update current_sector (Industry column
                # already provides it) but we DO update current_affil and
                # skip the row so its text doesn't become an entity name.
                # Section pattern: row has only 1-2 non-empty cells AND
                # the first cell contains text (not money). For (b) BDCs,
                # also require the text to look like a section header
                # (contains "Investments", " - N%", or affiliation tokens).
                is_section_row = (
                    len(non_empty) <= 2
                    and not looks_like_money(first_text)
                    and not first_text.startswith("$")
                    and any(c.isalpha() for c in first_text))
                if is_section_row and has_industry_col:
                    # Stricter check for BDCs with Industry column: only
                    # treat as section if text looks like a known section
                    # pattern (statistics row or affiliation header).
                    if not (re.search(r"\b\d+\.\d+\s*%", first_text)
                            or _parse_affiliation_header(first_text)
                            or re.match(r"^(Debt|Equity|Warrant|Investment) Investments?\b", first_text, re.I)
                            or re.match(r"^(1st|2nd|First|Second) Lien", first_text, re.I)
                            or re.match(r"^(United States|Canada|Europe|Asia|Africa|"
                                       r"Australia|United Kingdom|Germany|France|"
                                       r"Bermuda|Cayman|Mexico|Brazil|Japan|China|"
                                       r"India|Singapore|Switzerland|Netherlands)\b",
                                       first_text)):
                        is_section_row = False

                if is_section_row:
                    candidate = first_text.strip()
                    if (len(candidate) > 2
                            and not candidate.startswith("(")
                            and "Company" not in candidate
                            and "Description" not in candidate
                            and candidate not in
                            ("Interest", "Rate", "Cost", "Fair Value",
                             "Maturity", "Coupon", "Date", "Notes",
                             "Footnotes", "Shares", "Units")):
                        # Investment-type section headers (BDCs like BXSL/FSK
                        # that group by tranche type at section level).
                        inv_type = _parse_investment_type_header(candidate)
                        # Affiliation section headers
                        affil = _parse_affiliation_header(candidate)
                        # If this 1-cell row looks like a company name AND
                        # doesn't match any known section-header pattern,
                        # it's likely an issuer row (NMFC pattern: parent
                        # and subsidiary names each on their own row before
                        # the tranches). Capture as current_issuer.
                        looks_company = _looks_like_company_name(candidate)
                        if looks_company and not affil and not inv_type:
                            current_issuer = candidate
                            current_description = None
                            continue
                        if inv_type:
                            current_inv_type = inv_type
                        if affil:
                            current_affil = affil
                        elif not has_industry_col:
                            # Filter out candidates that look like company
                            # names (end with corporate suffix). Sectors
                            # typically don't have corp suffixes.
                            if not looks_company:
                                current_sector = candidate
                        current_issuer = None
                        current_description = None
                        continue

                fields = assign_cells_to_fields(cells, header_map)

                # If BDC has Industry column, take sector from that field
                row_sector = fields.get("industry", "").strip() or None
                effective_sector = row_sector or current_sector
                # Strip "(continued)" from sectors that wrap across pages
                if effective_sector:
                    effective_sector = re.sub(
                        r"\s*\((?:continued|cont\.?)\)\s*$", "",
                        effective_sector, flags=re.I).strip()

                company = (fields.get("company") or "").strip()
                description = (fields.get("description") or "").strip()
                if company:
                    cleaned = _FOOTNOTE_TAIL.sub("", company).strip()
                    # Strip "—<address>" suffix (OBDC pattern)
                    cleaned = re.sub(
                        r"\s*[—–-]\s*\d+\s+[A-Za-z].*$", "", cleaned).strip()
                    # Some filers (PSEC, MAIN) place tranche descriptors
                    # in the company column for continuation rows. Detect
                    # them and inherit current_issuer instead of treating
                    # the descriptor as a new issuer.
                    if cleaned and not looks_like_money(cleaned):
                        # NMFC pattern: the industry name appears in the
                        # company column on the FIRST tranche row of a
                        # company (e.g. "Consumer Services" alongside the
                        # type/spread cells). If the text doesn't look like
                        # a company name AND matches a known GICS sub-
                        # industry, treat as sector update — not a new
                        # issuer.
                        if (not _looks_like_tranche_descriptor(cleaned)
                                and not _looks_like_company_name(cleaned)
                                and _looks_like_industry_name(cleaned)
                                and current_issuer):
                            current_sector = cleaned
                            # Don't update current_issuer — keep the prior
                            # one from the parent/sub rows.
                        elif not _looks_like_tranche_descriptor(cleaned):
                            current_issuer = cleaned
                            current_description = (description.rstrip(".")
                                                   if description else None)

                if not current_issuer:
                    continue
                fv = extract_money(fields.get("fair_value"))
                if fv is None:
                    continue
                # Real position row indicators. If the filer has an
                # investment_type column, require it (drops sector
                # subtotal rows). Otherwise require principal/cost
                # to be present in this row (drops subtotal-only rows).
                if has_investment_type_col:
                    if not fields.get("investment_type"):
                        continue
                else:
                    if not (fields.get("principal")
                            or fields.get("cost")
                            or fields.get("shares")):
                        continue
                    # Also drop rows where the FV equals the issuer-aggregate
                    # subtotal (heuristic — actual sub-row would have less)

                coupon = fields.get("coupon", "")
                reference = fields.get("reference", "")
                spread = fields.get("spread", "")
                pik_field = fields.get("pik_rate", "")
                cash_field = fields.get("cash_rate", "")

                # Try multiple sources for interest rate / base rate / pik
                interest_rate = parse_rate(coupon) or parse_rate(cash_field)
                pik_rate = parse_pik_rate(coupon) or parse_rate(pik_field)
                base_rate = parse_base_rate(reference) or parse_base_rate(coupon)

                # Apply unit scaling — converts $K filers to $M
                scale = self.value_scale_m
                principal = extract_money(fields.get("principal"))
                cost_v = extract_money(fields.get("cost"))
                shares = extract_money(fields.get("shares"))
                pct_nav = extract_money(fields.get("pct_nav"))

                positions.append(ParsedRow(
                    bdc=self.ticker,
                    issuer=current_issuer,
                    sector=effective_sector,
                    affiliation=current_affil,
                    business_description=current_description,
                    investment_type=fields.get("investment_type") or current_inv_type,
                    base_rate=base_rate,
                    spread=parse_rate(spread),
                    interest_rate=interest_rate,
                    pik_rate=pik_rate,
                    rate_floor=parse_rate(fields.get("floor", "")),
                    acquisition_date=parse_date(fields.get("acq", "")),
                    maturity_date=parse_date(fields.get("maturity", "")),
                    shares_units=shares,           # shares aren't currency
                    principal=principal * scale if principal else None,
                    cost=cost_v * scale if cost_v else None,
                    fair_value=fv * scale,
                    pct_net_assets=pct_nav,        # percentage, no scale
                    footnotes=fields.get("footnotes"),
                ))

        return positions

    # ── Hooks for subclasses ──────────────────────────────────────────

    def _find_sector_in_prose(self, html_chunk: str) -> Optional[str]:
        """Look for known sectors in plain text between tables."""
        if not self.known_sectors:
            return None
        plain = re.sub(r"<[^>]+>", " ", html_chunk)
        plain = re.sub(r"\s+", " ", plain).strip()
        for sector in self.known_sectors:
            if sector in plain:
                return sector
        return None
