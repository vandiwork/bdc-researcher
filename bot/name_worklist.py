"""Generate the brand-name research worklist.

Emits the top-N borrowers by total fair value that still lack a brand/common
name AND are not already in the web-search cache (common_names_search.json) —
so re-runs only surface NEW borrowers from new filings. Each entry carries the
SOI business description + sector + holders as context, which is what lets a
researcher map an obscure holdco ("Zarya HoldCo, Inc.") to its operating brand
("Eptura").

Usage:  python bot/name_worklist.py [N]   # default N=1000
Writes: bot/name_worklist.json
"""
from __future__ import annotations
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENRICHED = SCRIPT_DIR / "out_all_enriched"
SEARCH_CACHE = SCRIPT_DIR / "common_names_search.json"
OUT = SCRIPT_DIR / "name_worklist.json"


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build(n: int = 1000) -> list[dict]:
    cache = (json.loads(SEARCH_CACHE.read_text(encoding="utf-8"))
             if SEARCH_CACHE.exists() else {})
    agg: dict[str, dict] = defaultdict(
        lambda: {"fv": 0.0, "desc": "", "sector": "", "cn": "", "bdcs": set()})
    for fp in ENRICHED.glob("*.csv"):
        for r in csv.DictReader(fp.open(encoding="utf-8")):
            e = (r.get("entity") or "").strip()
            if not e:
                continue
            a = agg[e]
            a["fv"] += _f(r.get("fv"))
            a["bdcs"].add(r.get("bdc", ""))
            d = (r.get("desc") or r.get("business_description") or "").strip()
            if len(d) > len(a["desc"]):
                a["desc"] = d
            s = (r.get("gics_industry_group") or r.get("gics_sector")
                 or r.get("sector") or "").strip()
            if s and not a["sector"]:
                a["sector"] = s
            if (r.get("common_name") or "").strip():
                a["cn"] = r["common_name"]
    ranked = sorted(agg.items(), key=lambda x: -x[1]["fv"])[:n]
    work = []
    for legal, a in ranked:
        if a["cn"]:           # already has a brand (filing dba or prior search)
            continue
        if legal in cache:    # already searched (incl. confirmed-blank "")
            continue
        work.append({
            "legal": legal,
            "fv_m": round(a["fv"] / 1000.0, 1),
            "sector": a["sector"],
            "desc": a["desc"],
            "holders": sorted(b for b in a["bdcs"] if b),
        })
    return work


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    work = build(n)
    OUT.write_text(json.dumps(work, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT.name}: {len(work)} borrowers to research "
          f"(top {n} by FV, minus already-named / already-cached)")
