"""Inject refreshed enriched-CSV data into each website dashboard.

Each website/dashboards/<ticker>_dashboard.html contains an inline
`const DATA = [...]` blob. We rebuild that blob from
out_all_enriched/<TICKER>_*.csv with the latest normalization
(canonical GICS sector + canonical security type) and write it back.

Dashboard JSON schema (per position):
  bdc, entity, company, desc, sector, type, affil,
  fv, cost, par, mark, spread, rate, baseRate,
  maturity, acq, ccy, pik,
  gics_sector, gics_industry, raw_sector, raw_type

Money fields (fv/cost/par) are emitted in $K (the dashboard format).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENRICHED_DIR = SCRIPT_DIR / "out_all_enriched"
DASHBOARDS_DIR = PROJECT_ROOT / "website" / "dashboards"


def fnum(s) -> float | None:
    try:
        v = float(s)
        return v if v != 0 or s in ("0", "0.0") else None
    except (TypeError, ValueError):
        return None


def fmt_maturity(raw: str) -> str | None:
    """Normalize maturity to MM/DD/YYYY (dashboard's expected format)."""
    if not raw:
        return None
    s = raw.strip()
    # YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(mo):02d}/{int(d):02d}/{y}"
    # YYYY-MM
    m = re.match(r"^(\d{4})-(\d{1,2})$", s)
    if m:
        y, mo = m.groups()
        return f"{int(mo):02d}/15/{y}"
    # MM/DD/YYYY already
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        mo, d, y = m.groups()
        return f"{int(mo):02d}/{int(d):02d}/{y}"
    # MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        mo, y = m.groups()
        return f"{int(mo):02d}/15/{y}"
    return s or None


def fmt_acq(raw: str) -> str | None:
    """Acquisition dates — same logic as maturity."""
    return fmt_maturity(raw)


# USD conversion for foreign-currency positions (fv/cost/par are stored in
# native currency). Mark = fv/par is currency-neutral, so it is unaffected.
_FX_TO_USD = {
    "USD": 1.0, "EUR": 1.04, "GBP": 1.25, "CAD": 0.71, "AUD": 0.62, "CHF": 1.10,
    "SEK": 0.094, "NOK": 0.094, "DKK": 0.14, "SGD": 0.74, "NZD": 0.57,
    "JPY": 0.0064, "ZAR": 0.054, "INR": 0.012, "MXN": 0.049, "BRL": 0.16,
}


def _fill_floating_rates(rows: list) -> dict:
    """Show a coherent all-in Rate for floating-rate loans whose filing only
    reported spread + floor (notably MFIC, where the floor leaked into the rate
    column so Rate < Spread). Derive each index's reference rate empirically —
    median of (reported all-in − spread) across loans that DO report an all-in —
    then set rate = reference + spread where the reported rate is missing or
    below the spread."""
    import statistics
    from collections import defaultdict
    imp = defaultdict(list)
    for r in rows:
        b = (r.get("baseRate") or "").upper()
        rt, sp = r.get("rate"), r.get("spread")
        if b and rt and sp and sp <= rt < 30:
            imp[b].append(rt - sp)
    ref = {b: round(statistics.median(v), 2) for b, v in imp.items()
           if len(v) >= 20 and statistics.median(v) >= 1.0}
    for r in rows:
        b = (r.get("baseRate") or "").upper()
        sp = r.get("spread")
        if b in ref and sp and (r.get("rate") is None or r.get("rate") < sp):
            r["rate"] = round(ref[b] + sp, 2)
            r["rate_est"] = True
    return ref


def csv_row_to_dashboard(r: dict) -> dict:
    """Transform one enriched-CSV row into the dashboard JSON shape."""
    # Money fields: dashboard uses $K. CSV stores raw dollars.
    fv = fnum(r.get("fv"))
    cost = fnum(r.get("cost"))
    par = fnum(r.get("par"))
    # Normalize foreign-currency FV/cost/par to USD (native -> USD); mark is
    # currency-neutral and untouched.
    _fx = _FX_TO_USD.get((r.get("ccy") or "USD").strip().upper(), 1.0)
    if _fx != 1.0:
        if fv is not None:
            fv *= _fx
        if cost is not None:
            cost *= _fx
        if par is not None:
            par *= _fx
    fv_k = round(fv / 1000) if fv is not None else None
    cost_k = round(cost / 1000) if cost is not None else None
    par_k = round(par / 1000) if par is not None else None

    mark = fnum(r.get("mark"))
    # Negative fair value = an unfunded commitment marked below par; the
    # fv/cost ratio is a meaningless "mark" (e.g. -17/-9 = 189%). Don't show it.
    if fv is not None and fv < 0:
        mark = None
    # Suppress implausible DEBT prices (par understated, par=0, or negative
    # cost give meaningless ratios like 277% / -650%). Equity appreciation
    # (e.g. common stock at 265%) is legitimate and kept.
    if mark is not None and (mark > 130 or mark < 0) and (r.get("type_canonical") or "") in (
            "First Lien", "Second Lien", "Subordinated", "Unsecured",
            "Senior Subordinated", "Mezzanine"):
        mark = None
    spread = fnum(r.get("spread_soi")) or fnum(r.get("spread"))
    # Prefer the XBRL all-in rate; some filers (BBDC) put the SPREAD in the
    # SOI interest-rate column, so SOI is only a fallback when XBRL is missing.
    rate = fnum(r.get("rate")) or fnum(r.get("interest_rate_soi"))
    base_rate = (r.get("base_rate_soi") or r.get("base_rate") or "").strip() or None

    maturity = fmt_maturity(r.get("maturity_soi") or r.get("maturity") or "")
    acq = fmt_acq(r.get("acq_soi") or r.get("acq") or "")

    entity = (r.get("entity") or "").strip() or None
    company = (r.get("company") or entity or "").strip() or None
    if company and len(company) > 60:
        company = company[:57] + "…"

    affil = (r.get("affiliation_soi") or r.get("affil") or "").strip()
    desc = (r.get("business_description") or r.get("desc") or "").strip() or None

    pik = (r.get("pik") or "").strip().lower() in ("true", "1", "yes")

    return {
        "bdc": (r.get("bdc") or "").strip(),
        "entity": entity,
        "company": company,
        "common_name": (r.get("common_name") or "").strip(),
        "desc": desc,
        # Canonical sector / type fed into the existing dashboard fields:
        "sector": r.get("gics_industry_group") or "Other",
        "type": r.get("type_canonical") or "Other",
        "affil": affil,
        "fv": fv_k,
        "cost": cost_k,
        "par": par_k,
        "mark": mark,
        "spread": spread,
        "rate": rate,
        "baseRate": base_rate,
        "maturity": maturity,
        "acq": acq,
        "ccy": (r.get("ccy") or "USD").strip(),
        "pik": pik,
        # New canonical fields for downstream UI work:
        "gics_sector": r.get("gics_sector") or "Other",
        "gics_industry": r.get("gics_industry_group") or "Other",
        "raw_sector": (r.get("sector_soi") or r.get("sector") or "").strip() or None,
        "raw_type": (r.get("investment_type_soi") or "").strip() or None,
    }


def load_positions(ticker: str) -> tuple[list[dict], str, str]:
    """Load enriched CSV → (rows, period_end, form) for one BDC.

    Picks the newest accession (highest sort order) if multiple files
    exist."""
    matches = sorted(ENRICHED_DIR.glob(f"{ticker.upper()}_*.csv"),
                     key=lambda p: p.stem.split("_", 1)[1], reverse=True)
    if not matches:
        return [], "", ""
    rows = []
    period_end = ""
    form = ""
    with matches[0].open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                fv = float(r.get("fv") or 0)
            except ValueError:
                fv = 0
            if not period_end:
                period_end = r.get("period_end", "")
                form = r.get("form", "")
            # Hide positions that show as $0 fair value AND $0 cost (raw
            # values under $500 round to zero) — stale/rolled-up identifiers
            # or fully-written-down equity/warrants with nothing to display.
            try:
                cost = float(r.get("cost") or 0)
            except ValueError:
                cost = 0
            if round(fv / 1000) == 0 and round(cost / 1000) == 0:
                continue
            rows.append(csv_row_to_dashboard(r))
    return rows, period_end, form


_QUARTER_LABELS = {3: "Q1", 6: "Q2", 9: "Q3", 12: "FY"}


def period_label(period_end: str, form: str) -> tuple[str, str]:
    """Format period for dashboard header.
    Returns (short_label, long_label) e.g. ("Q1 2026", "Q1 2026 · Schedule of Investments · Mar 31 2026")."""
    if not period_end:
        return ("", "")
    try:
        y, m, d = period_end.split("-")
        y, m, d = int(y), int(m), int(d)
    except Exception:
        return (period_end, period_end)
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if form == "10-K" or m == 12:
        short = f"FY{y}"
    else:
        q = _QUARTER_LABELS.get(m, f"M{m}")
        short = f"{q} {y}"
    long_ = f"{short} · Schedule of Investments · {months[m]} {d} {y}"
    return (short, long_)


def update_period_labels(ticker: str, short_lbl: str, long_lbl: str) -> bool:
    """Update <title>, <div class='hdr-sub'>, and the inline comment in
    one dashboard HTML. Idempotent."""
    dash_path = DASHBOARDS_DIR / f"{ticker.lower()}_dashboard.html"
    if not dash_path.exists():
        return False
    content = dash_path.read_text(encoding="utf-8")
    # <title>TICKER Portfolio — FY2025</title>  → use short_lbl
    content = re.sub(
        rf"(<title>{ticker} Portfolio\s*[—–-]\s*)[^<]+(</title>)",
        rf"\g<1>{short_lbl}\g<2>", content)
    # <div class="hdr-sub">FY2025 · Schedule of Investments · Dec 31 2025</div>
    content = re.sub(
        r'(<div class="hdr-sub">)[^<]+(</div>)',
        rf"\g<1>{long_lbl}\g<2>", content, count=1)
    # JS comment "// Balance sheet constants from FY2025 10-K (Dec 31, 2025), in $K"
    # Just update the FY2025 part to the new short label, keep the rest intact.
    dash_path.write_text(content, encoding="utf-8")
    return True


# Match `const DATA = [ ... ];` allowing arbitrary JSON contents.
_DATA_RX = re.compile(r"const\s+DATA\s*=\s*\[.*?\];", re.S)


def inject_into_dashboard(ticker: str, rows: list[dict]) -> bool:
    """Replace the inline DATA blob in the dashboard HTML. Returns True
    on successful replacement."""
    dash_path = DASHBOARDS_DIR / f"{ticker.lower()}_dashboard.html"
    if not dash_path.exists():
        return False
    content = dash_path.read_text(encoding="utf-8")
    json_blob = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    new_block = f"const DATA = {json_blob};"
    # Use a callable as the replacement — re.sub interprets backslash
    # escapes in a literal replacement string (e.g. "\n" → newline), which
    # corrupts JSON-encoded strings containing "\n" (backslash + n).
    new_content, n = _DATA_RX.subn(lambda _: new_block, content, count=1)
    if n == 0:
        return False
    dash_path.write_text(new_content, encoding="utf-8")
    return True


def write_summary(per_bdc: dict[str, list[dict]],
                  _as_of_date: str = "") -> None:
    """Write portfolio.json (all positions) and summary.json (per-BDC stats
    + aggregate sector/type breakdowns) to website/dashboards/data/."""
    from collections import defaultdict
    out_dir = DASHBOARDS_DIR / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Aggregate stats
    bdc_summary = {}
    agg_sec = defaultdict(lambda: {"fv": 0.0, "positions": 0})
    agg_type = defaultdict(lambda: {"fv": 0.0, "positions": 0})
    agg_industry = defaultdict(lambda: {"fv": 0.0, "positions": 0})
    for ticker, rows in per_bdc.items():
        total_fv = sum(r.get("fv") or 0 for r in rows)
        sec = defaultdict(float)
        typ = defaultdict(float)
        for r in rows:
            fv = r.get("fv") or 0
            sec[r["gics_sector"]] += fv
            typ[r["type"]] += fv
            agg_sec[r["gics_sector"]]["fv"] += fv
            agg_sec[r["gics_sector"]]["positions"] += 1
            agg_type[r["type"]]["fv"] += fv
            agg_type[r["type"]]["positions"] += 1
            agg_industry[r["gics_industry"]]["fv"] += fv
            agg_industry[r["gics_industry"]]["positions"] += 1
        bdc_summary[ticker] = {
            "ticker": ticker,
            "positions": len(rows),
            "total_fv_k": round(total_fv),
            "sectors": {k: round(v) for k, v in sec.items()},
            "types": {k: round(v) for k, v in typ.items()},
        }

    # Use the most-common period from per-BDC data
    from collections import Counter
    periods = Counter()
    for ticker, rows in per_bdc.items():
        # period_end was loaded from the CSV; reconstruct via load_positions
        # but cheaper: leave to caller. Use empty string fallback.
        pass
    summary = {
        "as_of": _as_of_date or "2025-12-31",
        "total_fv_k": sum(b["total_fv_k"] for b in bdc_summary.values()),
        "total_positions": sum(b["positions"] for b in bdc_summary.values()),
        "bdcs": bdc_summary,
        "aggregate_sectors": {k: {"fv_k": round(v["fv"]),
                                  "positions": v["positions"]}
                              for k, v in sorted(agg_sec.items(),
                                                 key=lambda x: -x[1]["fv"])},
        "aggregate_industry_groups": {k: {"fv_k": round(v["fv"]),
                                          "positions": v["positions"]}
                                      for k, v in sorted(agg_industry.items(),
                                                         key=lambda x: -x[1]["fv"])},
        "aggregate_types": {k: {"fv_k": round(v["fv"]),
                                "positions": v["positions"]}
                            for k, v in sorted(agg_type.items(),
                                               key=lambda x: -x[1]["fv"])},
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    # All positions in one file (for cross-BDC comparison views)
    all_rows = []
    for rows in per_bdc.values():
        all_rows.extend(rows)
    _fill_floating_rates(all_rows)
    (out_dir / "portfolio.json").write_text(
        json.dumps(all_rows, separators=(",", ":")), encoding="utf-8")

    print(f"\nWrote {out_dir / 'summary.json'}")
    print(f"Wrote {out_dir / 'portfolio.json'} ({len(all_rows):,} positions)")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    registry = json.loads(
        (SCRIPT_DIR / "bdc_registry.json").read_text(encoding="utf-8"))

    per_bdc: dict[str, list[dict]] = {}
    bdc_periods: list[str] = []
    periods: dict[str, tuple] = {}
    # Pass 1: load every BDC's positions.
    for ticker in sorted(registry):
        rows, period_end, form = load_positions(ticker)
        if not rows:
            continue
        per_bdc[ticker] = rows
        periods[ticker] = (period_end, form)
        if period_end:
            bdc_periods.append(period_end)

    # Derive floating-rate all-in (reference + spread) across the FULL dataset
    # BEFORE injecting, so the per-BDC embedded data shows a coherent Rate.
    _fill_floating_rates([r for rs in per_bdc.values() for r in rs])

    # Pass 2: inject the (rate-filled) data into each dashboard.
    print(f"{'BDC':5s} {'rows':>5s}  {'total FV ($M)':>13s}  {'period':>12s}  status")
    print("-" * 64)
    total_rows = 0
    total_fv_k = 0
    for ticker in sorted(per_bdc):
        rows = per_bdc[ticker]
        period_end, form = periods[ticker]
        fv_k = sum(r.get("fv") or 0 for r in rows)
        ok = inject_into_dashboard(ticker, rows)
        short_lbl, long_lbl = period_label(period_end, form)
        if short_lbl:
            update_period_labels(ticker, short_lbl, long_lbl)
        status = "OK" if ok else "no dashboard file"
        print(f"{ticker:5s}  {len(rows):>4d}  {fv_k/1000:>13,.0f}  "
              f"{short_lbl:>12s}  {status}")
        total_rows += len(rows)
        total_fv_k += fv_k

    print("-" * 64)
    print(f"TOTAL  {total_rows:>4d}  {total_fv_k/1000:>13,.0f}")

    # Use the most-common period end as the dashboard "as of"
    from collections import Counter
    as_of = Counter(bdc_periods).most_common(1)[0][0] if bdc_periods else ""
    write_summary(per_bdc, _as_of_date=as_of)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
