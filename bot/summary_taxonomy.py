"""Print per-BDC and aggregate breakdowns by canonical GICS sector +
canonical security type, with FV dollars.

Used to QA the W2 normalizer output."""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    sec_total_fv: Counter = Counter()
    type_total_fv: Counter = Counter()
    sec_total_count: Counter = Counter()
    type_total_count: Counter = Counter()
    bdc_sec_fv: dict[str, Counter] = defaultdict(Counter)
    bdc_type_fv: dict[str, Counter] = defaultdict(Counter)

    for fp in sorted((SCRIPT_DIR / "out_all_enriched").glob("*.csv")):
        bdc = fp.name.split("_")[0]
        with fp.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                fv = fnum(r.get("fv"))
                gs = r.get("gics_sector") or "Other"
                tc = r.get("type_canonical") or "Other"
                sec_total_fv[gs] += fv
                type_total_fv[tc] += fv
                sec_total_count[gs] += 1
                type_total_count[tc] += 1
                bdc_sec_fv[bdc][gs] += fv
                bdc_type_fv[bdc][tc] += fv

    total_fv = sum(sec_total_fv.values())
    total_pos = sum(sec_total_count.values())

    print("=" * 80)
    print(f"AGGREGATE BY GICS SECTOR  ({total_pos:,} positions, ${total_fv/1e9:.1f}B FV)")
    print("=" * 80)
    print(f"{'Sector':40s} {'Positions':>10s} {'FV ($M)':>12s} {'%FV':>7s}")
    for s in sorted(sec_total_fv, key=lambda k: -sec_total_fv[k]):
        print(f"  {s:38s} {sec_total_count[s]:>10,d} "
              f"{sec_total_fv[s]/1e6:>12,.0f} "
              f"{100*sec_total_fv[s]/total_fv:>6.1f}%")

    print()
    print("=" * 80)
    print(f"AGGREGATE BY CANONICAL SECURITY TYPE")
    print("=" * 80)
    print(f"{'Type':30s} {'Positions':>10s} {'FV ($M)':>12s} {'%FV':>7s}")
    for t in sorted(type_total_fv, key=lambda k: -type_total_fv[k]):
        print(f"  {t:28s} {type_total_count[t]:>10,d} "
              f"{type_total_fv[t]/1e6:>12,.0f} "
              f"{100*type_total_fv[t]/total_fv:>6.1f}%")

    print()
    print("=" * 80)
    print("PER-BDC SECTOR COVERAGE (% of FV mapped to GICS, vs. Other)")
    print("=" * 80)
    print(f"{'BDC':5s} {'Total FV ($M)':>14s} {'Known %':>9s} {'Other %':>10s}")
    for bdc in sorted(bdc_sec_fv):
        total = sum(bdc_sec_fv[bdc].values())
        unknown = bdc_sec_fv[bdc].get("Other", 0)
        known_pct = 100 * (total - unknown) / total if total else 0
        unk_pct = 100 * unknown / total if total else 0
        print(f"  {bdc:5s} {total/1e6:>12,.0f}  {known_pct:>7.1f}%  {unk_pct:>8.1f}%")

    print()
    print("=" * 80)
    print("PER-BDC TYPE COVERAGE (% of FV mapped to canonical, vs. Other)")
    print("=" * 80)
    print(f"{'BDC':5s} {'Total FV ($M)':>14s} {'Known %':>9s} {'Other %':>10s}")
    for bdc in sorted(bdc_type_fv):
        total = sum(bdc_type_fv[bdc].values())
        other = bdc_type_fv[bdc].get("Other", 0)
        known_pct = 100 * (total - other) / total if total else 0
        oth_pct = 100 * other / total if total else 0
        print(f"  {bdc:5s} {total/1e6:>12,.0f}  {known_pct:>7.1f}%  {oth_pct:>8.1f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
