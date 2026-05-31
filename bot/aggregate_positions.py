"""Aggregate identical tranches within each BDC.

Filers frequently report one facility across several Schedule-of-Investments
line items (funded vs. unfunded, multiple draws, add-ons). When two or more
rows for the SAME BDC differ only in amount — i.e. they share the same issuer,
security type, maturity, interest rate, spread, base rate, and currency — they
are the same economic exposure and are merged into a single row: fv / cost /
par / shares / fv_raw are summed and the mark (price) is recomputed.

This de-duplicates the per-BDC dashboards and keeps the cross-BDC views
(compare, mark-delta) consistent with them. Total FV per BDC is unchanged
(amounts are summed, not dropped), so the FV audit still foots.

Runs after apply_names.py; rewrites out_all_enriched/*.csv in place.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENRICHED = SCRIPT_DIR / "out_all_enriched"

# Numeric columns that are summed when rows are merged.
SUM_FIELDS = ("fv", "cost", "par", "shares", "fv_raw")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _key(r: dict) -> tuple:
    """Two rows merge iff they match on all of these — i.e. only the amount
    differs. Equity (blank maturity/rate) merges by issuer + type alone.

    Uses the CANONICAL / displayed fields (the same ones the dashboards show)
    so tranches that look identical to a user actually merge. In particular
    the raw `type` often carries a tranche index ("First Lien Term Loan 1",
    "... Term Loan 2", "... Revolver") which all display as "First Lien" — we
    key on type_canonical so they collapse into one position."""
    def soi(a, b):
        return (r.get(a) or r.get(b) or "").strip()
    return (
        (r.get("entity") or "").strip().lower(),
        (r.get("type_canonical") or r.get("type") or "").strip(),
        soi("maturity_soi", "maturity"),
        # rate: XBRL all-in first, then SOI — must match the dashboard's
        # displayed rate so rows that look identical actually merge.
        (str(r.get("rate") or "").strip() or str(r.get("interest_rate_soi") or "").strip()),
        soi("spread_soi", "spread"),
        soi("base_rate_soi", "base_rate"),
        (r.get("ccy") or "").strip(),
    )


def _merge(group: list[dict]) -> dict:
    base = dict(group[0])
    sums: dict[str, float | None] = {f: None for f in SUM_FIELDS}
    for r in group:
        for f in SUM_FIELDS:
            v = _f(r.get(f))
            if v is not None:
                sums[f] = (sums[f] or 0.0) + v
    for f in SUM_FIELDS:
        if sums[f] is not None:
            base[f] = sums[f]
    # Recompute mark = PRICE (fv/par) when plausible, else fv/cost — matching
    # extract_bdc_soi.py so the blended mark stays consistent with single rows.
    fv, par, cost = sums["fv"], sums["par"], sums["cost"]
    mark = None
    if fv is not None and par:
        price = fv / par * 100
        if 0 < price <= 130:
            mark = round(price, 2)
    if mark is None and fv is not None and cost:
        mark = round(fv / cost * 100, 2)
    base["mark"] = mark if mark is not None else ""
    return base


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    before = after = 0
    for fp in sorted(ENRICHED.glob("*.csv")):
        rows = list(csv.DictReader(fp.open(encoding="utf-8")))
        if not rows:
            continue
        cols = list(rows[0].keys())
        groups: dict[tuple, list[dict]] = {}
        order: list[tuple] = []
        for r in rows:
            k = _key(r)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(r)
        merged = [
            _merge(groups[k]) if len(groups[k]) > 1 else groups[k][0]
            for k in order
        ]
        before += len(rows)
        after += len(merged)
        with fp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(merged)
    print(f"aggregate_positions: {before} -> {after} rows "
          f"({before - after} identical tranches merged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
