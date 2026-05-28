"""Diagnostic: for each BDC, find the column headers of the SOI table
in its latest 10-K HTML document. Tells us what metadata each filer
discloses in the SOI."""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from lxml import etree, html as lhtml

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE = SCRIPT_DIR / ".cache" / "soi_headers"
CACHE.mkdir(parents=True, exist_ok=True)
UA = "BDC Researcher contact@example.com"


def fetch(url: str, sess: requests.Session, cache_key: str | None = None) -> bytes:
    if cache_key:
        cp = CACHE / cache_key
        if cp.exists() and cp.stat().st_size > 0:
            return cp.read_bytes()
    r = sess.get(url, timeout=300)
    r.raise_for_status()
    if cache_key:
        (CACHE / cache_key).write_bytes(r.content)
    return r.content


def find_latest_filing(cik: str, sess: requests.Session,
                        form: str = "10-K") -> dict | None:
    """Find latest filing of given form for this CIK. Form is "10-K" or "10-Q"."""
    sub_path = SCRIPT_DIR / ".cache" / f"submissions_{int(cik):010d}.json"
    if sub_path.exists():
        sub = json.loads(sub_path.read_text(encoding="utf-8"))
    else:
        sess.headers["Host"] = "data.sec.gov"
        try:
            r = sess.get(
                f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
                timeout=30)
            r.raise_for_status()
            sub = r.json()
        finally:
            sess.headers.pop("Host", None)
        sub_path.write_text(json.dumps(sub), encoding="utf-8")
    rec = sub["filings"]["recent"]
    for i, f in enumerate(rec["form"]):
        if f == form:
            return {
                "accession": rec["accessionNumber"][i],
                "primary": rec["primaryDocument"][i],
                "period": rec["reportDate"][i],
                "cik": cik,
            }
    return None


def find_latest_10k(cik: str, sess: requests.Session) -> dict | None:
    return find_latest_filing(cik, sess, "10-K")


def extract_soi_headers(html_bytes: bytes, ticker: str) -> list[list[str]]:
    """Find the SOI table(s) and extract column headers.

    Strategy: locate the heading containing 'Schedule of Investments'
    and walk forward to the first substantial <table>. Pull the first
    row that looks like a header row (contains words like 'Company',
    'Fair Value', 'Cost', 'Investment', or has bold styling).
    """
    # Decode safely
    text = html_bytes.decode("utf-8", errors="replace")

    # Find the first occurrence of "Schedule of Investments" (case insensitive)
    # in the document body. There may be table-of-contents references first;
    # skip those by requiring the heading is followed by a <table> within
    # the next ~50KB.
    headers_per_table: list[list[str]] = []
    soi_re = re.compile(
        r"(?i)(?:consolidated\s+)?schedule\s+of\s+investments")
    iter_count = 0
    for m in soi_re.finditer(text):
        iter_count += 1
        if iter_count > 30:
            break
        # Look in the next 200KB for a <table>
        snippet = text[m.start():m.start() + 250_000]
        # Skip if this is a TOC link (contains href= within 200 chars)
        head = text[max(0, m.start() - 50):m.start() + 200]
        if "href=" in head:
            continue

        # Find first <table> in snippet
        table_m = re.search(r"<table\b[^>]*>", snippet, re.IGNORECASE)
        if not table_m:
            continue
        # Find the matching </table>
        tbl_start = table_m.start()
        # Bounded chunk of HTML for this table (up to 1 MB)
        chunk = snippet[tbl_start:tbl_start + 1_000_000]
        end_m = re.search(r"</table>", chunk, re.IGNORECASE)
        if not end_m:
            continue
        table_html = chunk[: end_m.end()]

        # Parse the table
        try:
            doc = lhtml.fromstring(table_html)
        except Exception:
            continue

        # Pull rows. Pick the first row whose cells look like headers
        rows = doc.xpath("//tr")
        for row in rows[:15]:
            cells = row.xpath("./td|./th")
            texts = []
            for c in cells:
                t = " ".join(
                    s.strip()
                    for s in c.xpath(".//text()")
                    if s.strip()
                )
                texts.append(t)
            # Drop empty leading cells
            texts = [t for t in texts if t]
            if not texts:
                continue
            # Heuristic: header row has at least 3 cells and contains
            # at least one of these words
            blob = " ".join(texts).lower()
            keywords = (
                "company", "issuer", "portfolio", "industry", "investment",
                "fair value", "amortized cost", "cost", "principal",
                "maturity", "rate", "spread", "%", "reference",
            )
            if (len(texts) >= 3 and
                    any(k in blob for k in keywords)):
                headers_per_table.append(texts)
                break

        if len(headers_per_table) >= 5:
            break

    return headers_per_table


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", default="10-K", choices=("10-K", "10-Q"))
    args = ap.parse_args()

    registry = json.loads(
        (SCRIPT_DIR / "bdc_registry.json").read_text(encoding="utf-8"))
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})

    for ticker, info in registry.items():
        cik = info["cik"]
        try:
            filing = find_latest_filing(cik, sess, args.form)
            if not filing:
                print(f"\n[{ticker}] No {args.form} found")
                continue
            raw_acc = filing["accession"].replace("-", "")
            primary = filing["primary"]
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{raw_acc}/{primary}"
            )
            cache_key = f"{ticker}_{raw_acc}.htm"
            html_bytes = fetch(url, sess, cache_key=cache_key)
            headers = extract_soi_headers(html_bytes, ticker)
            print(f"\n=== {ticker}  (period {filing['period']}, accession {filing['accession']}) ===")
            print(f"  primary doc: {primary}  size {len(html_bytes):,}b")
            if not headers:
                print(f"  ⚠ No SOI table headers extracted")
                continue
            # Show unique header sets only
            seen = set()
            for h in headers:
                key = tuple(h)
                if key in seen:
                    continue
                seen.add(key)
                print(f"  Columns ({len(h)}):")
                for i, col in enumerate(h):
                    short = col[:100] + "…" if len(col) > 100 else col
                    print(f"    {i:2d}. {short!r}")
        except Exception as e:
            print(f"\n[{ticker}] ERROR: {type(e).__name__}: {e}")
        time.sleep(0.15)


if __name__ == "__main__":
    main()
