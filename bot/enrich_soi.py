"""Enrich XBRL-extracted positions with HTML SOI metadata.

The XBRL bot (extract_bdc_soi.py) produces canonical position records
with reliable FV/cost/rate data. The HTML SOI parser (soi_html/) walks
each filer's main 10-K HTML to extract sector, maturity, acquisition
date, base rate, business description, and footnotes — fields that
aren't tagged in XBRL.

This script joins the two:

  1. Reads bot/out_all/<TICKER>_<accession>.csv (XBRL positions)
  2. Runs the matching HTML parser on the 10-K
  3. Joins each XBRL position to the closest HTML row by (issuer key,
     FV in $K) within tolerance
  4. Backfills the new metadata fields
  5. Writes bot/out_all_enriched/<TICKER>_<accession>.csv

Rows from the HTML side that don't match any XBRL position (subtotal
rows, page footers, etc.) are simply dropped from the join — the XBRL
position list is the canonical source of truth.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import soi_html   # noqa: E402
from soi_html._base import ParsedRow  # noqa: E402
from normalize import (  # noqa: E402
    classify_position, normalize_type)


# ── Helpers ───────────────────────────────────────────────────────────

_SUFFIX_RE = re.compile(
    r"\s*[,(].*?(?:Inc|LLC|L\.?P\.?|LP|Ltd|GmbH|S\.A\.?R\.L|B\.V|"
    r"Corp|Corporation|Holdings|Holding|Group)\.?\s*$", re.I)
_PAREN_RE = re.compile(r"\s*\([^)]*\)")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


_ADDRESS_TAIL = re.compile(
    r"\s*[—\-]\s*\d+\s+[A-Za-z].*?(?:Street|Avenue|Boulevard|Road|"
    r"Drive|Way|Place|Lane|Court|Suite|Floor|Plaza|Highway|"
    r"\d{5}(?:-\d{4})?)\s*[A-Za-z\s,.\d-]*$", re.I)


def issuer_key(name: str) -> str:
    """Normalize an issuer name for fuzzy matching across XBRL and HTML."""
    if not name:
        return ""
    # OBDC and a few others put a physical address after an em-dash —
    # "AAM Series 1.1 Rail..., LLC—1100 Highland Drive, Boca Raton..."
    # Strip the address tail.
    name = _ADDRESS_TAIL.sub("", name)
    s = name.lower()
    s = _PAREN_RE.sub("", s)         # remove parenthetical asides
    s = _PUNCT_RE.sub(" ", s)        # punctuation -> space
    s = _WS_RE.sub(" ", s).strip()
    # Drop common corporate suffixes for matching
    s = re.sub(r"\b(inc|llc|lp|ltd|corp|corporation|holdings?|holdco|"
               r"topco|midco|bidco|s a r l|gmbh|b v|ulc)\b\.?", "", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def build_html_index(rows: list[ParsedRow]
                     ) -> dict[tuple[str, int], list[ParsedRow]]:
    """Index HTML rows by (issuer_key, fv_K) for fast lookup."""
    idx: dict[tuple[str, int], list[ParsedRow]] = defaultdict(list)
    for r in rows:
        if r.fair_value is None:
            continue
        key = (issuer_key(r.issuer), int(round(r.fair_value * 1000)))
        idx[key].append(r)
    return idx


def find_html_match(
    bot_issuer: str,
    bot_fv_K: float,
    idx: dict[tuple[str, int], list[ParsedRow]],
    fv_only_idx: dict[int, list[ParsedRow]],
) -> Optional[ParsedRow]:
    """Find the best HTML row for a given XBRL position.

    FV match tolerance: ±max($5K, 1% of value). HTML SOIs often round to
    1 decimal place in $M, so a $100M position can differ by up to $50K
    between sources."""
    fv = int(round(bot_fv_K))
    key_ent = issuer_key(bot_issuer)
    fv_tol = max(5, int(abs(fv) * 0.01))

    # 1. Exact (issuer, FV) match within tolerance
    for delta in range(-fv_tol, fv_tol + 1):
        candidates = idx.get((key_ent, fv + delta))
        if candidates:
            return candidates[0]

    # 2. FV-bucket match — find HTML rows with matching FV
    bucket: list[ParsedRow] = []
    for delta in range(-fv_tol, fv_tol + 1):
        bucket.extend(fv_only_idx.get(fv + delta, []))
    if len(bucket) == 1:
        return bucket[0]
    # Among multiple FV matches, pick the one whose normalized issuer
    # contains tokens from the XBRL issuer
    if bucket and key_ent:
        bot_tokens = set(key_ent.split())
        scored = []
        for r in bucket:
            html_tokens = set(issuer_key(r.issuer).split())
            overlap = len(bot_tokens & html_tokens)
            if overlap > 0:
                scored.append((overlap, r))
        if scored:
            scored.sort(key=lambda x: -x[0])
            return scored[0][1]
        # Fall back to first FV-bucket hit
        return bucket[0]

    # 3. Token-overlap match — XBRL entity may include sector/affiliation
    # text that's not in HTML issuer (e.g. MFIC's
    # "Aerospace & Defense Beaufort Eagle U.S. Purchaser, Inc." vs HTML's
    # "Beaufort Eagle U.S. Purchaser, Inc."). Score by overlap of
    # significant tokens (length >= 4).
    if key_ent:
        bot_tokens = {t for t in key_ent.split() if len(t) >= 4}
        if bot_tokens:
            best: tuple[int, ParsedRow] | None = None
            for (ent_key, html_fv), candidates in idx.items():
                if abs(html_fv - fv) > 5:
                    continue
                html_tokens = {t for t in ent_key.split() if len(t) >= 4}
                overlap = len(bot_tokens & html_tokens)
                if overlap >= 2:
                    if best is None or overlap > best[0]:
                        best = (overlap, candidates[0])
            if best:
                return best[1]
    return None


# ── Main ──────────────────────────────────────────────────────────────

def enrich_one(ticker: str, xbrl_csv: Path, html_bytes: bytes,
               out_dir: Path) -> dict:
    """Enrich one BDC's positions. Returns stats dict."""
    parser = soi_html.get(ticker)
    if parser is None:
        return {"ticker": ticker, "error": "no HTML parser"}

    html_rows = parser.parse_soi(html_bytes)
    idx = build_html_index(html_rows)
    # Build secondary FV-only index for fallback matching
    fv_only_idx: dict[int, list[ParsedRow]] = defaultdict(list)
    for r in html_rows:
        if r.fair_value is None:
            continue
        fv_only_idx[int(round(r.fair_value * 1000))].append(r)

    with xbrl_csv.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        positions = list(reader)

    # Add enrichment columns to the CSV schema
    enrich_cols = [
        "sector_soi", "affiliation_soi", "investment_type_soi",
        "base_rate_soi", "maturity_soi", "acq_soi", "business_description",
        "rate_floor_soi", "footnotes", "pct_net_assets_soi",
        "interest_rate_soi", "spread_soi", "pik_rate_soi",
        "gics_sector", "gics_industry_group", "type_canonical",
    ]
    for c in enrich_cols:
        if c not in cols:
            cols.append(c)

    matched = 0
    eligible = 0   # positions with non-zero FV (only these are joinable)
    for p in positions:
        try:
            # Match against the UNSCALED fair value when present. FSK/MSDL
            # have their fv reconciled (scaled) to the filer's reported
            # total; fv_raw preserves the original SOI value the HTML rows
            # carry, so enrichment matching is unaffected by the scale.
            raw = p.get("fv_raw")
            fv_K = float(raw if raw not in (None, "") else p["fv"]) / 1000.0
        except (KeyError, ValueError, TypeError):
            continue
        if fv_K == 0:
            continue
        eligible += 1
        match = find_html_match(p["entity"], fv_K, idx, fv_only_idx)
        if not match:
            continue
        matched += 1
        # Always capture HTML-derived fields as <field>_soi columns —
        # don't suppress when XBRL also has them (lets us cross-check
        # and prefer HTML for missing XBRL fields downstream).
        if match.sector:
            p["sector_soi"] = match.sector
        if match.investment_type:
            p["investment_type_soi"] = match.investment_type
        if match.base_rate:
            p["base_rate_soi"] = match.base_rate
        if match.maturity_date:
            p["maturity_soi"] = match.maturity_date
        if match.acquisition_date:
            p["acq_soi"] = match.acquisition_date
        if match.business_description:
            p["business_description"] = match.business_description
        if match.rate_floor:
            p["rate_floor_soi"] = match.rate_floor
        if match.footnotes:
            p["footnotes"] = match.footnotes
        if match.pct_net_assets is not None:
            p["pct_net_assets_soi"] = match.pct_net_assets
        if match.affiliation:
            p["affiliation_soi"] = match.affiliation
        if match.interest_rate is not None:
            p["interest_rate_soi"] = match.interest_rate
        if match.spread is not None:
            p["spread_soi"] = match.spread
        if match.pik_rate is not None:
            p["pik_rate_soi"] = match.pik_rate

    # ── Canonical taxonomy normalization ──
    # Apply to every position (matched or not). Entity-based Black Box
    # detection takes precedence (JV / CLO / fund-of-funds positions).
    # Otherwise prefer XBRL raw sector, fall back to HTML-side.
    # Web-searched sector overrides for borrowers whose filing carries no
    # usable sector/description (heavy on MAIN equity co-investments).
    # Keyed by legal name; value = [gics_sector, industry_group].
    try:
        _sector_overrides = json.loads(
            (SCRIPT_DIR / "sector_overrides.json").read_text(encoding="utf-8"))
    except Exception:
        _sector_overrides = {}

    for p in positions:
        entity = (p.get("entity") or p.get("company") or "").strip()
        xbrl_sec = (p.get("sector") or "").strip()
        soi_sec = (p.get("sector_soi") or "").strip()
        desc = (p.get("business_description") or p.get("desc") or "").strip()
        gics, ig = classify_position(entity, xbrl_sec, soi_sec, desc)
        ov = _sector_overrides.get(entity)
        if ov and (ig in ("Other", "", None)):
            gics, ig = ov[0], ov[1]
        p["gics_sector"] = gics
        p["gics_industry_group"] = ig

        xbrl_t = (p.get("type") or "").strip()
        soi_t = (p.get("investment_type_soi") or "").strip()
        tc_x = normalize_type(xbrl_t) if xbrl_t else "Other"
        if tc_x == "Other":
            tc = normalize_type(soi_t) if soi_t else "Other"
        else:
            tc = tc_x
        p["type_canonical"] = tc

    # ── Entity-level sector fill ──
    # All tranches of one borrower share a sector, but filers tag it on
    # only the (first) debt tranche, leaving equity/warrant tranches blank
    # -> "Other" (heavy on PSEC, MAIN). Propagate the most common non-Other
    # sector within each borrower to its "Other"/blank siblings.
    from collections import Counter as _Counter
    by_entity: dict[str, _Counter] = {}
    for p in positions:
        ent = (p.get("entity") or "").strip().lower()
        g = p.get("gics_industry_group")
        if ent and g and g not in ("Other", ""):
            by_entity.setdefault(ent, _Counter())[(p.get("gics_sector"), g)] += 1
    for p in positions:
        if (p.get("gics_industry_group") or "Other") != "Other":
            continue
        ent = (p.get("entity") or "").strip().lower()
        c = by_entity.get(ent)
        if c:
            (gs, ig), _ = c.most_common(1)[0]
            p["gics_sector"] = gs
            p["gics_industry_group"] = ig

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / xbrl_csv.name
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in positions:
            w.writerow(p)

    return {
        "ticker": ticker,
        "xbrl_positions": len(positions),
        "eligible": eligible,
        "html_rows": len(html_rows),
        "matched": matched,
        "match_rate": matched / eligible if eligible else 0,
        "output": str(out_csv),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    # Auto-import all soi_html parsers
    registry = json.loads(
        (SCRIPT_DIR / "bdc_registry.json").read_text(encoding="utf-8"))
    for t in registry:
        try:
            __import__(f"soi_html.{t.lower()}")
        except ImportError:
            pass

    xbrl_dir = SCRIPT_DIR / "out_all"
    cache_dir = SCRIPT_DIR / ".cache" / "soi_headers"
    out_dir = SCRIPT_DIR / "out_all_enriched"

    print(f"{'BDC':5s} {'XBRL':>5s} {'elig':>5s} {'HTML':>5s} {'matched':>8s} {'rate':>6s}  status")
    print("-" * 56)
    for ticker in registry:
        xbrl_files = list(xbrl_dir.glob(f"{ticker}_*.csv"))
        if not xbrl_files:
            print(f"{ticker:5s}  no XBRL CSV — run extract_bdc_soi.py --all first")
            continue
        # Pick the HTML file whose accession matches this XBRL file's
        # accession. The XBRL CSV name is like "ARCC_000162828026027688.csv";
        # the matching cached HTML is "ARCC_000162828026027688.htm".
        xbrl_path = xbrl_files[0]
        accession = xbrl_path.stem.split("_", 1)[1]
        matched_html = cache_dir / f"{ticker}_{accession}.htm"
        if matched_html.exists():
            html_path = matched_html
        else:
            html_files = list(cache_dir.glob(f"{ticker}_*.htm"))
            if not html_files:
                print(f"{ticker:5s}  no cached HTML — run diag_soi_headers.py first")
                continue
            html_path = html_files[0]
        try:
            stats = enrich_one(
                ticker, xbrl_path, html_path.read_bytes(), out_dir)
        except Exception as e:
            print(f"{ticker:5s}  ERROR {type(e).__name__}: {e}")
            continue
        if "error" in stats:
            print(f"{ticker:5s}  {stats['error']}")
            continue
        rate = stats["match_rate"] * 100
        status = "OK" if rate >= 85 else ("WARN" if rate >= 50 else "LOW")
        print(f"{ticker:5s} {stats['xbrl_positions']:>5d} "
              f"{stats['eligible']:>5d} {stats['html_rows']:>5d} "
              f"{stats['matched']:>8d} {rate:>5.1f}%  {status}")

    print(f"\nWrote enriched CSVs to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
