"""Refresh data on top-level (cross-BDC) website pages.

Updates the following pages with Q1 2026 data + corrected text labels:
  - analytics.html  : ALL_DATA = {ticker: [position_rows]}
  - compare.html    : ALL_DATA = {ticker: [position_rows]}
  - markdelta.html  : ALL_DATA = [cross-BDC company overlaps]
  - pairs.html      : D.totals and D.books (preserves D.pnav from market data)
  - overlap.html    : recompute cross-holdings matrix
  - comps.html      : refresh NAV/Debt/GAV per row
  - dashboards.html : update footer date
  - index.html      : update header + footer dates

Run after enrich_soi.py + build_dashboards.py + extract_balance_sheet.py.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
WEBSITE = PROJECT_ROOT / "website"
ENRICHED_DIR = SCRIPT_DIR / "out_all_enriched"

# Period labels — these should match the Q1 dashboards
OLD_DATE_STRINGS = [
    "Dec 31 2025",
    "Dec 31, 2025",
    "December 31 2025",
    "December 31, 2025",
    "2025-12-31",
]
NEW_DATE = "Mar 31 2026"
NEW_DATE_COMMA = "Mar 31, 2026"
NEW_DATE_ISO = "2026-03-31"


def fnum(s) -> float | None:
    try:
        v = float(s)
        return v if v != 0 or s in ("0", "0.0") else None
    except (TypeError, ValueError):
        return None


def fmt_maturity(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(mo):02d}/{int(d):02d}/{y}"
    m = re.match(r"^(\d{4})-(\d{1,2})$", s)
    if m:
        y, mo = m.groups()
        return f"{int(mo):02d}/15/{y}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        mo, d, y = m.groups()
        return f"{int(mo):02d}/{int(d):02d}/{y}"
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        mo, y = m.groups()
        return f"{int(mo):02d}/15/{y}"
    return s or None


def csv_row_to_dashboard(r: dict) -> dict:
    """Same shape as build_dashboards.csv_row_to_dashboard."""
    fv = fnum(r.get("fv"))
    cost = fnum(r.get("cost"))
    par = fnum(r.get("par"))
    fv_k = round(fv / 1000) if fv is not None else None
    cost_k = round(cost / 1000) if cost is not None else None
    par_k = round(par / 1000) if par is not None else None
    mark = fnum(r.get("mark"))
    spread = fnum(r.get("spread_soi")) or fnum(r.get("spread"))
    rate = fnum(r.get("interest_rate_soi")) or fnum(r.get("rate"))
    base_rate = (r.get("base_rate_soi") or r.get("base_rate") or "").strip() or None
    maturity = fmt_maturity(r.get("maturity_soi") or r.get("maturity") or "")
    acq = fmt_maturity(r.get("acq_soi") or r.get("acq") or "")
    entity = (r.get("entity") or "").strip() or None
    company = (r.get("company") or entity or "").strip() or None
    affil = (r.get("affiliation_soi") or r.get("affil") or "").strip()
    desc = (r.get("business_description") or r.get("desc") or "").strip() or None
    pik = (r.get("pik") or "").strip().lower() in ("true", "1", "yes")
    return {
        "bdc": (r.get("bdc") or "").strip(),
        "entity": entity, "company": company, "desc": desc,
        "sector": r.get("gics_industry_group") or "Other",
        "type": r.get("type_canonical") or "Other",
        "affil": affil,
        "fv": fv_k, "cost": cost_k, "par": par_k, "mark": mark,
        "spread": spread, "rate": rate, "baseRate": base_rate,
        "maturity": maturity, "acq": acq,
        "ccy": (r.get("ccy") or "USD").strip(), "pik": pik,
        "gics_sector": r.get("gics_sector") or "Other",
        "gics_industry": r.get("gics_industry_group") or "Other",
    }


def load_all_data() -> dict[str, list[dict]]:
    """Read each enriched CSV; return {ticker: [rows]}."""
    all_data: dict[str, list[dict]] = {}
    # Use the most-recent CSV per ticker
    seen: dict[str, Path] = {}
    for fp in sorted(ENRICHED_DIR.glob("*.csv")):
        ticker = fp.name.split("_")[0]
        accession = fp.stem.split("_", 1)[1]
        prev = seen.get(ticker)
        if prev is None or accession > prev.stem.split("_", 1)[1]:
            seen[ticker] = fp
    for ticker, fp in seen.items():
        rows = []
        with fp.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    fv = float(r.get("fv") or 0)
                except ValueError:
                    fv = 0
                if fv == 0 and not r.get("cost") and not r.get("par"):
                    continue
                rows.append(csv_row_to_dashboard(r))
        all_data[ticker] = rows
    return all_data


def load_bs() -> dict[str, dict]:
    """Load Q1 balance-sheet facts."""
    p = SCRIPT_DIR / "bs_q1.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_market() -> dict[str, dict]:
    """Load latest market data from Yahoo Finance (built by
    extract_market_data.py)."""
    p = SCRIPT_DIR / "market_q1.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _f(v, suffix="", spec=",.0f"):
    """Format a number for display; '—' if None."""
    if v is None:
        return "—"
    try:
        return f"{v:{spec}}{suffix}"
    except Exception:
        return str(v)


def _signed_pct(v):
    """Format a signed % with .1f precision; '—' if None."""
    if v is None:
        return "—"
    return f"{v:+.1f}%"


# ── PAGE-SPECIFIC INJECTORS ──────────────────────────────────────────


def inject_all_data(page_name: str, all_data: dict) -> bool:
    """For analytics.html and compare.html — replace ALL_DATA blob."""
    fp = WEBSITE / page_name
    if not fp.exists():
        return False
    content = fp.read_text(encoding="utf-8")
    json_blob = json.dumps(all_data, separators=(",", ":"), ensure_ascii=False)
    new_block = f"const ALL_DATA = {json_blob};"
    pattern = re.compile(r"const ALL_DATA\s*=\s*\{.*?\};", re.S)
    new_content, n = pattern.subn(lambda _: new_block, content, count=1)
    if n == 0:
        return False
    fp.write_text(new_content, encoding="utf-8")
    return True


def build_markdelta_data(all_data: dict) -> list[dict]:
    """Compute cross-BDC company overlaps with min/max marks.

    For each company name held by 2+ BDCs, output:
      {company, type, type_class, holders, spread, min_mark, min_bdc,
       max_mark, max_bdc, total_fv, details: [{bdc, fv, mark, spread}]}
    """
    # Normalize company key
    def keyfn(c: str) -> str:
        s = (c or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[.,]", "", s)
        s = re.sub(r"\s+(inc|llc|lp|corp|ltd|holdings?)$", "", s)
        return s.strip()

    type_class_map = {
        "First Lien": "t1", "Second Lien": "t2", "Subordinated": "t3",
        "Mezzanine": "t3", "Unsecured": "t3",
        "Common Equity": "tEq", "Preferred Equity": "tEq",
        "Warrant": "tEq", "Structured Credit": "tCLO", "Other": "tO",
    }

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    company_names: dict[tuple, str] = {}
    for ticker, rows in all_data.items():
        for r in rows:
            cname = (r.get("company") or r.get("entity") or "").strip()
            if not cname or not r.get("fv"):
                continue
            k = (keyfn(cname), r.get("type") or "Other")
            buckets[k].append({
                "bdc": ticker,
                "fv": r["fv"],
                "mark": r.get("mark"),
                "spread": r.get("spread"),
                "company": cname,
            })
            company_names.setdefault(k, cname)

    out = []
    for k, entries in buckets.items():
        bdcs = sorted(set(e["bdc"] for e in entries))
        if len(bdcs) < 2:
            continue
        marks = [e["mark"] for e in entries if e["mark"] is not None]
        if not marks:
            continue
        ckey, type_ = k
        # Pick the most common display name
        name = company_names[k]
        total_fv = sum(e["fv"] for e in entries)
        marks_with_bdc = [(e["mark"], e["bdc"]) for e in entries
                          if e["mark"] is not None]
        marks_with_bdc.sort()
        min_mark, min_bdc = marks_with_bdc[0]
        max_mark, max_bdc = marks_with_bdc[-1]
        # Avg spread across all entries with a spread
        spreads = [e["spread"] for e in entries if e["spread"] is not None]
        avg_spread = round(sum(spreads) / len(spreads), 2) if spreads else None
        # Details — one per BDC, aggregated
        per_bdc: dict[str, dict] = {}
        for e in entries:
            d = per_bdc.setdefault(e["bdc"], {"bdc": e["bdc"], "fv": 0,
                                              "marks": [], "spreads": []})
            d["fv"] += e["fv"]
            if e["mark"] is not None:
                d["marks"].append(e["mark"])
            if e["spread"] is not None:
                d["spreads"].append(e["spread"])
        details = []
        for d in per_bdc.values():
            m = round(sum(d["marks"]) / len(d["marks"]), 2) if d["marks"] else None
            s = round(sum(d["spreads"]) / len(d["spreads"]), 2) if d["spreads"] else None
            details.append({"bdc": d["bdc"], "fv": round(d["fv"]),
                            "mark": m, "spread": s})
        details.sort(key=lambda x: -x["fv"])
        out.append({
            "company": name,
            "type": type_,
            "type_class": type_class_map.get(type_, "tO"),
            "holders": len(bdcs),
            "spread": avg_spread,
            "min_mark": round(min_mark, 2),
            "min_bdc": min_bdc,
            "max_mark": round(max_mark, 2),
            "max_bdc": max_bdc,
            "total_fv": round(total_fv),
            "details": details,
        })
    # Sort: most holders first, then total_fv
    out.sort(key=lambda x: (-x["holders"], -x["total_fv"]))
    return out


def inject_markdelta(md_data: list) -> bool:
    fp = WEBSITE / "markdelta.html"
    if not fp.exists():
        return False
    content = fp.read_text(encoding="utf-8")
    json_blob = json.dumps(md_data, separators=(",", ":"), ensure_ascii=False)
    new_block = f"var ALL_DATA = {json_blob};"
    pattern = re.compile(r"var ALL_DATA\s*=\s*\[.*?\];", re.S)
    new_content, n = pattern.subn(lambda _: new_block, content, count=1)
    if n == 0:
        return False
    fp.write_text(new_content, encoding="utf-8")
    return True


def _borrower_key(name: str) -> str:
    """Normalize a borrower name so the same issuer matches across BDCs
    that spell it slightly differently. Drops punctuation, common
    corporate suffixes, and parenthetical aliases."""
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"\s*\((?:dba|d/b/a|fka|f/k/a|aka|a/k/a)\b[^)]*\)", "", s)
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    s = re.sub(r"[.,'`]", "", s)
    s = re.sub(r"\s+&\s+", " and ", s)
    suffix_rx = re.compile(
        r"\s+(?:inc|llc|l\s*l\s*c|lp|l\s*p|ltd|limited|corp|corporation|"
        r"plc|gmbh|sarl|s\s*a\s*r\s*l|s\s*a|b\s*v|n\s*v|company|co|"
        r"holdings?|holdco|topco|midco|bidco|group)$",
        re.I)
    for _ in range(3):
        new = suffix_rx.sub("", s).strip()
        if new == s:
            break
        s = new
    return re.sub(r"\s+", " ", s).strip()


# Full BDC names for the pairs.html summary blurb
BDC_FULL_NAMES = {
    "ARCC": "Ares Capital Corporation",
    "BBDC": "Barings BDC",
    "BCRED": "Blackstone Private Credit Fund",
    "BCSF": "Bain Capital Specialty Finance",
    "BXSL": "Blackstone Secured Lending",
    "CGBD": "Carlyle Secured Lending",
    "FSK":  "FS KKR Capital Corp",
    "GBDC": "Golub Capital BDC",
    "GSBD": "Goldman Sachs BDC",
    "HTGC": "Hercules Capital",
    "MAIN": "Main Street Capital",
    "MFIC": "MidCap Financial Investment",
    "MSDL": "Morgan Stanley Direct Lending",
    "NMFC": "New Mountain Finance",
    "OBDC": "Blue Owl Capital Corporation",
    "OCSL": "Oaktree Specialty Lending",
    "PSEC": "Prospect Capital",
    "SLRC": "SLR Investment Corp",
    "TCPC": "BlackRock TCP Capital",
    "TRIN": "Trinity Capital",
    "TSLX": "Sixth Street Specialty Lending",
    "WHF":  "WhiteHorse Finance",
}


def build_pairs_data(all_data: dict, existing_pnav: dict,
                      bs_data: dict = None, market_data: dict = None) -> dict:
    """Build D = {pnav, totals, books, names} for pairs.html.

    Books are keyed by a normalized borrower key so the same issuer
    matches across BDCs that spell it slightly differently. pnav is
    recomputed from market price / Q1 NAV/share when both inputs are
    available; otherwise we preserve the existing market-data value.
    """
    pnav = dict(existing_pnav)
    bs_data = bs_data or {}
    market_data = market_data or {}
    for tk in set(list(bs_data.keys()) + list(market_data.keys())):
        nps = bs_data.get(tk, {}).get("nav_per_share")
        price = market_data.get(tk, {}).get("price")
        if nps and price:
            pnav[tk] = round(price / nps, 2)

    totals = {tk: sum(r.get("fv") or 0 for r in rows)
              for tk, rows in all_data.items()}
    books: dict[str, dict] = {}
    for tk, rows in all_data.items():
        book: dict[str, dict] = {}
        for r in rows:
            cname = (r.get("company") or r.get("entity") or "").strip()
            if not cname or not r.get("fv"):
                continue
            key = _borrower_key(cname)
            if not key:
                continue
            d = book.setdefault(key, {
                "name": cname,
                "sector": r.get("sector", "Other"),
                "type": r.get("type", "Other"),
                "fv": 0, "cost": 0, "par": 0,
            })
            d["fv"] += r.get("fv") or 0
            d["cost"] += r.get("cost") or 0
            d["par"] += r.get("par") or 0
        books[tk] = book
    names = {tk: BDC_FULL_NAMES.get(tk, tk) for tk in pnav}
    return {"pnav": pnav, "totals": totals, "books": books, "names": names}


def inject_pairs(pairs_data: dict) -> bool:
    fp = WEBSITE / "pairs.html"
    if not fp.exists():
        return False
    content = fp.read_text(encoding="utf-8")
    json_blob = json.dumps(pairs_data, separators=(",", ":"), ensure_ascii=False)
    new_block = f"const D = {json_blob};"
    pattern = re.compile(r"const D\s*=\s*\{.*?\};\s*\n", re.S)
    new_content, n = pattern.subn(lambda _: new_block + "\n", content, count=1)
    if n == 0:
        return False
    fp.write_text(new_content, encoding="utf-8")
    return True


def extract_existing_pnav() -> dict:
    """Pull pnav values from pairs.html (we don't have a market-data
    source so we preserve the existing values)."""
    fp = WEBSITE / "pairs.html"
    if not fp.exists():
        return {}
    content = fp.read_text(encoding="utf-8")
    m = re.search(r'"pnav":\s*(\{[^}]+\})', content)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def update_date_strings(filepath: Path) -> bool:
    """Replace stale date references in page text."""
    if not filepath.exists():
        return False
    content = filepath.read_text(encoding="utf-8")
    orig = content
    # Order matters — longer patterns first
    replacements = [
        ("December 31, 2025", NEW_DATE_COMMA),
        ("December 31 2025", NEW_DATE),
        ("Dec. 31, 2025", NEW_DATE_COMMA),
        ("Dec 31, 2025", NEW_DATE_COMMA),
        ("Dec 31 2025", NEW_DATE),
        ("2025-12-31", NEW_DATE_ISO),
    ]
    for old, new in replacements:
        content = content.replace(old, new)
    if content != orig:
        filepath.write_text(content, encoding="utf-8")
        return True
    return False


# ── COMPS.HTML refresh ───────────────────────────────────────────────


def update_comps(bs_data: dict, market_data: dict, all_data: dict) -> bool:
    """Refresh all market-data + BS columns in comps.html per ticker.

    Cells in each row after the ticker link <td>: Name, Price, Today,
    MTD, YTD, LTM, P/GAV, P/NAV, GAV, Debt, NAV, LTV, DivYield,
    PullToPar, 1yr@NAV.

    Indices into the post-link captured group: [0]=Name … [14]=1yrNAV.
    """
    fp = WEBSITE / "comps.html"
    if not fp.exists():
        return False
    content = fp.read_text(encoding="utf-8")

    n_updated = 0
    for ticker, bs in bs_data.items():
        if not all((bs.get("nav"), bs.get("gross_debt"))):
            continue
        nav_m = bs["nav"] / 1e6
        debt_m = bs["gross_debt"] / 1e6
        gav_m = (bs["nav"] + bs.get("total_liabilities", 0)) / 1e6
        ltv = debt_m / gav_m * 100 if gav_m else None
        nps = bs.get("nav_per_share")

        mk = market_data.get(ticker) or {}
        price = mk.get("price")
        today = mk.get("today_pct")
        mtd = mk.get("mtd_pct")
        ytd = mk.get("ytd_pct")
        ltm = mk.get("ltm_pct")
        div_y = mk.get("div_yield_pct")

        # P/NAV = market price / NAV per share
        p_nav = price / nps if (price and nps) else None
        # P/GAV = (price × shares) / GAV. GAV = NAV + liabilities.
        shares = bs.get("shares") or 0
        p_gav = (price * shares / (gav_m * 1e6)) if (price and shares and gav_m) else None

        # Pull to par = FV-weighted distance to par for marked debt
        # positions. Exclude positions with abnormally high marks (>200%)
        # which are typically small-cost-basis revolvers / equity-like —
        # they're not "pulling to par" since they aren't fixed-income.
        # Also restrict to debt positions only.
        rows = all_data.get(ticker, [])
        debt_types = {"First Lien", "Second Lien", "Subordinated",
                      "Mezzanine", "Unsecured"}
        marked = [(r.get("mark"), r.get("fv") or 0)
                  for r in rows
                  if r.get("type") in debt_types
                  and r.get("mark") is not None
                  and r.get("fv")
                  and -50 <= (r.get("mark") or 0) <= 150]
        if marked:
            tot_fv = sum(fv for _, fv in marked)
            wtd_mark = sum(m * fv for m, fv in marked) / tot_fv
            pull_to_par = round(100 - wtd_mark, 2)  # % left to recover
        else:
            pull_to_par = None

        # 1yr @ NAV: theoretical total return if discount closes plus div yield
        # = (1/P_NAV - 1)*100 + div_yield
        if p_nav and div_y:
            close_disc = (1 / p_nav - 1) * 100
            total_1yr = round(close_disc + div_y, 2)
        else:
            total_1yr = None

        def colored_pct(v):
            if v is None: return '<td class="num">—</td>'
            cls = "num pos" if v >= 0 else "num neg"
            return f'<td class="{cls}">{v:+.1f}%</td>'

        def colored_x(v, lo=0.95):
            if v is None: return '<td class="num">—</td>'
            cls = "num"
            if v < lo:
                return f'<td class="num"><span class="pnav-lo">{v:.2f}x</span></td>'
            return f'<td class="{cls}">{v:.2f}x</td>'

        # Build replacement cells (indices 0..14 in the captured group)
        new_cells = {
            1: f'<td class="num">${price:,.2f}</td>' if price else '<td class="num">—</td>',
            2: colored_pct(today),
            3: colored_pct(mtd),
            4: colored_pct(ytd),
            5: colored_pct(ltm),
            6: f'<td class="num">{p_gav:.2f}x</td>' if p_gav else '<td class="num">—</td>',
            7: colored_x(p_nav, lo=0.95),
            8: f'<td class="num">{gav_m:,.0f}</td>',
            9: f'<td class="num">{debt_m:,.0f}</td>',
            10: f'<td class="num">{nav_m:,.0f}</td>',
            11: f'<td class="num">{ltv:.1f}%</td>' if ltv else '<td class="num">—</td>',
            12: colored_pct(div_y),
            13: colored_pct(pull_to_par),
            14: colored_pct(total_1yr),
        }

        tr_pattern = re.compile(
            rf'(<a href="dashboards/{ticker.lower()}_dashboard\.html"[^>]*>{ticker}</a>'
            r'.*?</tr>)', re.S | re.I)
        m = tr_pattern.search(content)
        if not m:
            continue
        tr_block = m.group(1)
        td_positions = [(tm.start(), tm.end())
                        for tm in re.finditer(r'<td[^>]*>.*?</td>', tr_block, re.S)]
        if len(td_positions) < 15:
            continue
        result = list(tr_block)
        # Replace in reverse so earlier indices remain valid
        for i in sorted(new_cells.keys(), reverse=True):
            s, e = td_positions[i]
            result[s:e] = new_cells[i]
        new_tr = "".join(result)
        content = content[:m.start(1)] + new_tr + content[m.end(1):]
        n_updated += 1

    # Update the price/data-as-of label in the header sub
    as_of = next((d.get("as_of") for d in market_data.values()
                  if d.get("as_of")), "")
    if as_of:
        # Parse YYYY-MM-DD → "Mon DD, YYYY"
        try:
            from datetime import datetime
            ds = datetime.strptime(as_of, "%Y-%m-%d").strftime("%b %d, %Y")
        except Exception:
            ds = as_of
        # Update any "Price as of …" / "Market data" caption
        content = re.sub(
            r'(P/NAV from )[^·\n<]+',
            rf'\1pricing on {ds}',
            content)

    if n_updated > 0:
        fp.write_text(content, encoding="utf-8")
    return n_updated > 0


# ── MAIN ─────────────────────────────────────────────────────────────


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("Refreshing cross-BDC site pages with Q1 2026 data\n")

    all_data = load_all_data()
    bs_data = load_bs()
    market_data = load_market()
    print(f"Loaded {len(all_data)} BDCs, "
          f"{sum(len(v) for v in all_data.values()):,} positions, "
          f"{len(bs_data)} BS records, {len(market_data)} market records")

    # 1. analytics.html, compare.html — same ALL_DATA shape
    for page in ("analytics.html", "compare.html"):
        ok = inject_all_data(page, all_data)
        print(f"  ALL_DATA → {page:18s} {'OK' if ok else 'SKIP (no match)'}")

    # 2. markdelta.html
    md = build_markdelta_data(all_data)
    ok = inject_markdelta(md)
    print(f"  ALL_DATA → markdelta.html       {'OK' if ok else 'SKIP'} "
          f"({len(md)} overlapping companies)")

    # 3. pairs.html — uses computed P/NAV when market data available,
    # falls back to existing values otherwise
    existing_pnav = extract_existing_pnav()
    pairs = build_pairs_data(all_data, existing_pnav, bs_data, market_data)
    ok = inject_pairs(pairs)
    computed = sum(1 for tk in pairs["pnav"]
                   if bs_data.get(tk, {}).get("nav_per_share")
                   and market_data.get(tk, {}).get("price"))
    print(f"  D        → pairs.html           {'OK' if ok else 'SKIP'} "
          f"(pnav: {computed} computed from market, "
          f"{len(pairs['pnav']) - computed} preserved)")

    # 4. comps.html — refresh BS + market columns
    if bs_data:
        ok = update_comps(bs_data, market_data, all_data)
        print(f"  comps    → comps.html           {'OK' if ok else 'SKIP'}")

    # 5. Date strings across all top-level pages
    print()
    print("Updating date strings:")
    for fp in sorted(WEBSITE.glob("*.html")):
        if update_date_strings(fp):
            print(f"  updated {fp.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
