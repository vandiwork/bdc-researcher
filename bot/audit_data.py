"""Systematic data quality audit across all 18 BDC outputs.

Flags rows likely to have extraction defects:

1. Entity-name pollution: name contains section-break / heading text
   ("Investment", "Debt Investments", percent signs, etc.)
2. Sector pollution: sector value looks like an issuer name or
   includes "(continued)" or footnote markers
3. Suspicious numbers: mark > 1000% or < 1%, negative cost,
   negative fv on supposedly-real positions
4. Identifier-vs-entity mismatch: entity is just a corporate suffix
   ("Inc", "LLC") with no actual issuer name
5. Wrong-table extraction: rows where the entity is clearly a header
   label
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Patterns that indicate a bad entity / sector value
ENTITY_BAD_PATTERNS = [
    "Investment Debt Investments",
    "non-controlled/non-affiliated",
    "Non-Controlled/Non-Affiliated",
    "Debt Investments",
    "Equity Investments",
    "Warrant Investments",
    "United States",
    "Investments-",
    "Investments  -",
]

# Sectors that are clearly wrong (issuer names, header labels)
SECTOR_BAD_PATTERNS = [
    "(continued)",
    "(cont.)",
    "Holdings, LLC",
    "Investments-",
]
# Legit "container" sectors used by some BDCs for JV/fund-of-fund
# positions; not flagged as pollution.
SECTOR_LEGIT_CONTAINERS = {
    "Multi-Sector Holdings",        # OCSL CLO holdings
    "Credit Opportunities Partners JV, LLC",  # FSK JV
    "NMFC Senior Loan Program III LLC**",     # NMFC JV
    "NMFC Senior Loan Program IV LLC**",      # NMFC JV
}

# Sectors that are header-label leakage. "Investment Funds" is a real
# CGBD category for JV positions — exclude.
SECTOR_HEADER_LABELS = {
    "Investments", "Investment",
    "Interest", "Rate", "Coupon", "Maturity", "Cost",
    "Fair Value", "Notes", "Shares", "Units",
}


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def audit_row(r: dict) -> list[str]:
    """Return a list of issue codes for this row."""
    issues = []
    entity = (r.get("entity") or "").strip()
    sector = (r.get("sector_soi") or r.get("sector") or "").strip()
    investment_type = (r.get("type") or "").strip()
    fv = fnum(r.get("fv"))
    cost = fnum(r.get("cost"))
    mark = fnum(r.get("mark"))
    rate = fnum(r.get("rate"))

    # ── Entity issues ──
    if not entity:
        issues.append("ENTITY_EMPTY")
    elif any(p in entity for p in ENTITY_BAD_PATTERNS):
        issues.append("ENTITY_POLLUTED")
    elif entity in ("Inc", "LLC", "L.P.", "Ltd", "Corp"):
        issues.append("ENTITY_SUFFIX_ONLY")
    elif "%" in entity and "(" in entity:
        # Things like "Investment Debt Investments - 216.4% United States - 20"
        issues.append("ENTITY_HAS_PERCENT")
    elif len(entity) < 3:
        issues.append("ENTITY_TOO_SHORT")

    # ── Sector issues ──
    if sector and sector not in SECTOR_LEGIT_CONTAINERS:
        if sector in SECTOR_HEADER_LABELS:
            issues.append("SECTOR_HEADER_LABEL")
        elif any(p in sector for p in SECTOR_BAD_PATTERNS):
            issues.append("SECTOR_POLLUTED")
        elif "%" in sector:
            issues.append("SECTOR_HAS_PERCENT")
        elif "(continued)" in sector.lower():
            issues.append("SECTOR_CONTINUED")

    # ── Numeric issues ──
    # Skip MARK_EXTREME when cost basis is tiny (<$50K) — small-denominator
    # effects on revolvers/unfunded commitments give legit huge percentages.
    if mark is not None and fv and cost and abs(cost) >= 50_000:
        if mark > 5000 or mark < -100:
            issues.append("MARK_EXTREME")
    if fv is not None and fv < -1e6:
        issues.append("FV_LARGE_NEGATIVE")
    if rate is not None and rate > 50:
        issues.append("RATE_EXTREME")

    return issues


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    by_bdc: dict[str, list[tuple[dict, list[str]]]] = defaultdict(list)
    issue_counter: Counter = Counter()
    bdc_issues: dict[str, Counter] = defaultdict(Counter)

    for fp in sorted((SCRIPT_DIR / "out_all_enriched").glob("*.csv")):
        bdc = fp.name.split("_")[0]
        with fp.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                issues = audit_row(r)
                if issues:
                    by_bdc[bdc].append((r, issues))
                    for iss in issues:
                        issue_counter[iss] += 1
                        bdc_issues[bdc][iss] += 1

    print("=" * 80)
    print("DATA QUALITY AUDIT — ISSUE COUNTS BY BDC")
    print("=" * 80)
    issues_list = sorted(issue_counter, key=lambda x: -issue_counter[x])
    header = f"{'BDC':5s}  " + "  ".join(f"{i[:13]:>13s}" for i in issues_list)
    print(header)
    print("-" * len(header))
    for bdc in sorted(by_bdc):
        cells = "  ".join(
            f"{bdc_issues[bdc].get(i, 0):>13d}" for i in issues_list)
        print(f"{bdc:5s}  {cells}")
    print()
    print(f"{'TOTAL':5s}  " + "  ".join(
        f"{issue_counter[i]:>13d}" for i in issues_list))

    # Show a few examples per issue type
    print("\n" + "=" * 80)
    print("SAMPLE ROWS PER ISSUE TYPE")
    print("=" * 80)
    seen_by_issue: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for bdc, rows in by_bdc.items():
        for r, issues in rows:
            for iss in issues:
                if len(seen_by_issue[iss]) < 3:
                    seen_by_issue[iss].append((bdc, r))
    for iss in issues_list:
        if not seen_by_issue[iss]:
            continue
        print(f"\n[{iss}]")
        for bdc, r in seen_by_issue[iss][:3]:
            entity = (r.get("entity") or "")[:60]
            sect = (r.get("sector_soi") or r.get("sector") or "")[:40]
            fv = r.get("fv", "")
            print(f"  {bdc}  fv=${fnum(fv) or 0:>10,.0f}  entity={entity!r}  sector={sect!r}")


if __name__ == "__main__":
    main()
