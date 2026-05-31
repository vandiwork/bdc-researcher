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
# An UNCLOSED former-name parenthetical (a per-BDC parser cut the identifier
# mid-paren), e.g. "FL Hawk ..., Inc. (f/k/a Fineline Technologies". Strip from
# the "(f/k/a" to end of string.
_FKA_OPEN = re.compile(r"\s*\((?:fka|f/k/a|formerly(?:\s+known\s+as)?)\b.*$", re.I)
# Any leftover parenthetical to strip from the legal name for display.
_ANY_PAREN = re.compile(r"\s*\([^)]*\)")

# Unambiguous *terminal* corporate suffixes (ones that end a legal entity name,
# not mid-name words like "Group"/"Holdings"/"Company" which would truncate too
# early). Used to detect multi-borrower strings the filers list as one entity,
# e.g. "Cloud Software Group, Inc., Picard Parent, Inc., Cloud Software Group
# Holdings, ...". We keep only the FIRST (primary) borrower.
_TERM_SUFFIX = (
    r"(?:Inc|LLC|L\.?L\.?C|LLP|L\.?L\.?P|LP|L\.?P|Ltd|Limited|Corp|Corporation"
    r"|Incorporated|S\.?A|S\.?A\.?R\.?L|N\.?V|B\.?V|GmbH|AG|S\.?p\.?A|plc"
    r"|Pty|Cooperatief|U\.?A|AB|ApS|Oy)"
)
# First terminal suffix that is immediately followed by another capitalised
# entity (", X..." / " and X..." / " & X...") → multiple co-borrowers.
# case-insensitive so ALL-CAPS suffixes ("LTD", "PLC") are caught too; the
# suffix-before-separator requirement is what prevents false positives on
# names like "Berner Food & Beverage, LLC" (no suffix before the "&").
_MULTI_BORROWER = re.compile(
    r"^(.*?\b" + _TERM_SUFFIX + r"\.?)\s*(?:,\s+(?:and\s+)?|\s+and\s+|\s*&\s+)[A-Z\[]",
    re.I,
)
# Instrument/class descriptor appended after a spaced hyphen / en / em dash,
# e.g. "Axsome Therapeutics, Inc. - Common Stock", "1988 CLO 3, Ltd. - Class
# ER". Real legal names don't use a spaced dash, so cut at the first one.
_DESC_DASH = re.compile(r"\s[\-–—]\s")


def primary_legal(legal: str) -> str:
    """Collapse a multi-co-borrower legal string to its primary (first) entity.

    Filers sometimes list every obligor on a tranche as one comma/'and'-joined
    blob. We keep the first complete legal entity (through its terminal
    corporate suffix) and drop the rest. No-ops on single-entity names.
    """
    m = _MULTI_BORROWER.match(legal)
    if m:
        cand = m.group(1).strip().rstrip(",").strip()
        # Guard against pathological 2-char captures; require something real.
        if len(cand) >= 5:
            return cand
    return legal


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
    legal = _FKA_OPEN.sub("", legal)
    # Truncate any residual " | <sector/tranche/affiliation>" suffix that a
    # per-BDC parser left on the entity (BBDC "| Revolver", PSEC "| <sector>",
    # BXSL "| Non-Affiliated Issuer", etc.). A real company name never
    # contains " | ".
    # A real company name never contains a pipe; cut at the first one
    # (parsers use it as a field separator, sometimes without spaces, e.g.
    # "...LLC |First lien senior secured loan").
    legal = legal.split("|")[0]
    # Drop trailing instrument/class descriptor after a spaced dash.
    legal = _DESC_DASH.split(legal)[0]
    legal = re.sub(r"\s{2,}", " ", legal).strip()
    # Drop trailing pipe/comma artifacts left by parsers.
    legal = legal.rstrip(" |,").strip()
    # Collapse multi-co-borrower blobs to the primary entity.
    legal = primary_legal(legal)
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
    # overlay web-search results (only where no filing dba already set).
    # Normalise cache keys through primary_legal so entries written before the
    # multi-borrower truncation still resolve to the truncated legal name.
    for legal, common in search.items():
        key = primary_legal(legal.split(" | ")[0].strip())
        if common and key not in final:
            final[key] = common
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
