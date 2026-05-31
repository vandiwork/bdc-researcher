"""Post-enrichment pass: set the legal name as the canonical entity/company
and attach the resolved common/brand name (filing dba + web-search cache).

Runs after enrich_soi.py. Rewrites out_all_enriched/*.csv in place:
  - entity / company  -> legal name (dba/fka parenthetical stripped)
  - common_name (new) -> brand name (plain = high conf, [..] = low conf, '' = none)
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

from resolve_names import split_name

SCRIPT_DIR = Path(__file__).resolve().parent
ENRICHED = SCRIPT_DIR / "out_all_enriched"
COMMON = SCRIPT_DIR / "common_names.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    lookup = json.loads(COMMON.read_text(encoding="utf-8")) if COMMON.exists() else {}
    n_files = n_common = 0
    for fp in sorted(ENRICHED.glob("*.csv")):
        rows = list(csv.DictReader(fp.open(encoding="utf-8")))
        if not rows:
            continue
        cols = list(rows[0].keys())
        if "common_name" not in cols:
            cols.append("common_name")
        if "legal_name" not in cols:
            cols.append("legal_name")
        for r in rows:
            raw = (r.get("entity") or "").strip()
            legal, common_filing = split_name(raw)
            common = common_filing or lookup.get(legal, "")
            r["entity"] = legal
            r["company"] = legal
            r["legal_name"] = legal
            r["common_name"] = common
            if common:
                n_common += 1
        with fp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        n_files += 1
    print(f"apply_names: {n_files} files, {n_common} positions tagged with a common name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
