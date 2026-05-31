"""Resolve borrower common/brand names for the dashboard grey line.

Two sources:
  1. dba/fka/aka parentheticals embedded in the filing legal name
     (high confidence, no web search).
  2. A web-searched cache (common_names_search.json) for the largest
     positions that lack an embedded dba — populated by parallel research
     agents, low-conviction entries wrapped in [brackets].

Outputs:
  - bot/common_names.json  : {legal_name: common_name}  (merged, final)
  - prints the search work-list (top-N by FV without a dba) when run with
    --worklist N

`split_name(raw)` -> (legal, common_from_filing) is the canonical helper
imported by enrich_soi.py.
"""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# Read RAW extractor output (entities still carry their dba/fka parentheticals;
# apply_names.py later strips them in out_all_enriched).
ENRICHED = SCRIPT_DIR / "out_all"
SEARCH_CACHE = SCRIPT_DIR / "common_names_search.json"
OUT = SCRIPT_DIR / "common_names.json"

# "(dba X)", "(d/b/a X)", "(aka X)" -> X is the operating/brand name.
_DBA = re.compile(r"\s*\((?:dba|d/b/a|a/k/a|aka)\s+([^)]+)\)", re.I)
# "(fka X)", "(f/k/a X)", "(formerly ... X)" -> X is a former/recognisable name.
_FKA = re.compile(r"\s*\((?:fka|f/k/a|formerly(?:\s+known\s+as)?)\s+([^)]+)\)", re.I)
# Any leftover parenthetical to strip from the legal name for display.
_ANY_PAREN = re.compile(r"\s*\([^)]*\)")


def split_name(raw: str) -> tuple[str, str]:
    """(legal_name, common_name_from_filing).

    common is taken from a "(dba/aka X)" only — that's the operating brand.
    "(fka X)" is stripped from the legal name but NOT used as the common
    name: fka is ambiguous (sometimes the old brand, sometimes a former
    holdco codename), so the grey line is left to the web-search cache.
    """
    if not raw:
        return "", ""
    common = ""
    m = _DBA.search(raw)
    if m:
        common = m.group(1).strip()
    # Legal name = raw minus dba/fka parentheticals (keep other parentheticals
    # that are part of the legal name, e.g. "(US)").
    legal = _DBA.sub("", raw)
    legal = _FKA.sub("", legal)
    legal = re.sub(r"\s{2,}", " ", legal).strip().rstrip(",").strip()
    # Don't echo the common name if it's identical to the legal name.
    if common and common.lower() == legal.lower():
        common = ""
    return legal, common


def _fnum(s):
    try:
        return float(s or 0)
    except (TypeError, ValueError):
        return 0.0


def build_final() -> dict:
    """Merge filing-dba names + web-search cache into common_names.json."""
    search = {}
    if SEARCH_CACHE.exists():
        search = json.loads(SEARCH_CACHE.read_text(encoding="utf-8"))
    final: dict[str, str] = {}
    legals: set[str] = set()
    for fp in ENRICHED.glob("*.csv"):
        for r in csv.DictReader(fp.open(encoding="utf-8")):
            raw = (r.get("entity") or "").strip()
            if not raw:
                continue
            legal, common = split_name(raw)
            legals.add(legal)
            if common:
                final.setdefault(legal, common)
    # overlay web-search results (only where no filing dba already set)
    for legal, common in search.items():
        if common and legal not in final:
            final[legal] = common
    OUT.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    return final


def worklist(n: int) -> list[str]:
    """Top-N positions by FV whose entity has no filing dba and no cached
    search result -> unique legal names to web-search."""
    search = json.loads(SEARCH_CACHE.read_text(encoding="utf-8")) if SEARCH_CACHE.exists() else {}
    rows = []
    for fp in ENRICHED.glob("*.csv"):
        for r in csv.DictReader(fp.open(encoding="utf-8")):
            raw = (r.get("entity") or "").strip()
            if not raw:
                continue
            legal, common = split_name(raw)
            rows.append((_fnum(r.get("fv")), legal, common))
    rows.sort(key=lambda x: -x[0])
    seen, work = set(), []
    for fv, legal, common in rows:
        if legal in seen:
            continue
        seen.add(legal)
        if common or legal in search:
            continue
        work.append(legal)
        if len(work) >= n:
            break
    return work


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if len(sys.argv) > 2 and sys.argv[1] == "--worklist":
        wl = worklist(int(sys.argv[2]))
        print(json.dumps(wl, ensure_ascii=False, indent=2))
    else:
        final = build_final()
        print(f"Wrote {OUT.name}: {len(final)} common names "
              f"({sum(1 for v in final.values() if not v.startswith('['))} high-conf, "
              f"{sum(1 for v in final.values() if v.startswith('['))} bracketed)")
