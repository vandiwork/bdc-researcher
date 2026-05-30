"""Fetch BDC-related news headlines from Bloomberg, FT and WSJ.

Those three are hard-paywalled with no public API, and the site is a
static GitHub Pages app (no backend), so the only viable mechanism is
Google News RSS with `site:` domain filters. It returns each publisher's
HEADLINE + a link that resolves to the original article (the reader's own
subscription handles the paywall). This is free, server-side fetchable in
CI, and uses only headlines + links.

Output: bot/news.json
  {
    "fetched_utc": null,             # stamped by CI; no Date.now in build
    "sources": ["Bloomberg", "Financial Times", "WSJ"],
    "items": [
      {"title", "url", "source", "published", "published_iso",
       "tickers": [...], "category": "general"|"company"}
    ]
  }
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (compatible; BDC-Researcher news aggregator)"

# Publishers we surface (Google News `site:` filter + post-fetch domain gate).
SOURCES = {
    "Bloomberg":       ["bloomberg.com"],
    "Financial Times": ["ft.com"],
    "WSJ":             ["wsj.com"],
}
_ALLOWED_DOMAINS = {d for ds in SOURCES.values() for d in ds}

# Tracked BDCs: ticker -> (query name, [aliases for title relevance]).
BDCS = {
    "ARCC":  ("Ares Capital",                   ["Ares Capital", "ARCC", "Ares Management"]),
    "OBDC":  ("Blue Owl Capital",               ["Blue Owl", "OBDC"]),
    "BCRED": ("Blackstone Private Credit Fund",  ["Blackstone Private Credit", "BCRED"]),
    "FSK":   ("FS KKR Capital",                 ["FS KKR", "FSK", "FS Investment"]),
    "BXSL":  ("Blackstone Secured Lending",     ["Blackstone Secured Lending", "BXSL"]),
    "GBDC":  ("Golub Capital BDC",              ["Golub Capital", "GBDC"]),
    "PSEC":  ("Prospect Capital",               ["Prospect Capital", "PSEC"]),
    "MAIN":  ("Main Street Capital",            ["Main Street Capital", "MAIN"]),
    "HTGC":  ("Hercules Capital",               ["Hercules Capital", "HTGC"]),
    "TSLX":  ("Sixth Street Specialty Lending", ["Sixth Street Specialty", "TSLX", "Sixth Street"]),
    "GSBD":  ("Goldman Sachs BDC",              ["Goldman Sachs BDC", "GSBD"]),
    "BBDC":  ("Barings BDC",                    ["Barings BDC", "BBDC"]),
    "NMFC":  ("New Mountain Finance",           ["New Mountain Finance", "NMFC"]),
    "OCSL":  ("Oaktree Specialty Lending",      ["Oaktree Specialty", "OCSL"]),
    "BCSF":  ("Bain Capital Specialty Finance", ["Bain Capital Specialty", "BCSF"]),
    "CGBD":  ("Carlyle Secured Lending",        ["Carlyle Secured Lending", "CGBD"]),
    "MFIC":  ("MidCap Financial Investment",    ["MidCap Financial", "MFIC", "Apollo Investment"]),
    "MSDL":  ("Morgan Stanley Direct Lending",  ["Morgan Stanley Direct Lending", "MSDL"]),
    "TCPC":  ("BlackRock TCP Capital",          ["BlackRock TCP", "TCP Capital", "TCPC"]),
}

GENERAL_QUERIES = [
    '"business development company" private credit',
    "BDC private credit dividend",
    "private credit direct lending BDC",
]

_DOMAIN_CLAUSE = "(" + " OR ".join(f"site:{d}" for d in _ALLOWED_DOMAINS) + ")"

_BDC_KEYWORDS = re.compile(
    r"\b(BDC|business development compan|private credit|direct lending|"
    r"middle market|NAV|net asset value|leveraged loan|CLO)\b", re.I)

# Non-article noise Google News surfaces: stock-quote/profile pages and
# securities-class-action lawyer spam. Drop these.
_NOISE = re.compile(
    r"(stock price|\(u\.s\.:|nasdaq:|nyse:|\bquote\b|profile and biograph|"
    r"price target|price today|shares? outstanding|"
    r"annual cash flow|cash flow statement|balance sheet|income statement|"
    r"\bearnings estimate|dividend history|key statistics|"
    r"investor deadline|lead plaintiff|substantial losses|"
    r"class action|investigat(es|ion|ing) .* on behalf|securities fraud|"
    r"reminds investors|encourages investors|notifies investors)", re.I)

# Mojibake lead bytes: UTF-8 0xE2 decoded as cp1252 -> U+00E2 ("a-circumflex"),
# 0xC3 -> U+00C3 ("A-tilde"). Detect by codepoint so it never depends on this
# file's own encoding.
_MOJIBAKE_LEADS = ("â", "Ã")


def _repair_run(run: str) -> str:
    try:
        return run.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return run


def _fix_mojibake(s: str) -> str:
    """Repair UTF-8-as-Windows-1252 garbling. Reverses the round-trip on each
    cp1252-encodable run, so a genuine unicode char elsewhere in the string
    can't break the whole-string encode, and a real standalone accented char
    (whose lone cp1252 byte isn't valid UTF-8) is left intact."""
    if not any(ord(c) in (0xE2, 0xC3) for c in s):
        return s
    out, buf = [], []
    for ch in s:
        try:
            ch.encode("cp1252")
            buf.append(ch)
        except UnicodeEncodeError:
            out.append(_repair_run("".join(buf)))
            buf = []
            out.append(ch)
    out.append(_repair_run("".join(buf)))
    return "".join(out)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=25).read()


def _gnews_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _source_for(item: ET.Element):
    src = item.find("source")
    if src is None:
        return None, None
    src_url = src.get("url", "") or ""
    domain = urllib.parse.urlparse(src_url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    for disp, domains in SOURCES.items():
        if any(domain.endswith(d) for d in domains):
            return disp, domain
    return None, None


def _parse_date(s: str):
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), dt.timestamp()
    except Exception:
        return "", 0.0


def _clean_title(title: str) -> str:
    title = _fix_mojibake(title)
    if " - " in title:
        title = re.sub(r"\s+-\s+[^-]+$", "", title)
    return title.strip()


def _norm_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def fetch_query(query: str, *, want_keywords: bool, aliases):
    try:
        root = ET.fromstring(_fetch(_gnews_url(query)))
    except Exception as e:
        print(f"  query failed ({query[:40]}...): {type(e).__name__}: {e}")
        return []
    out = []
    for it in root.findall(".//item"):
        disp, _ = _source_for(it)
        if disp is None:
            continue
        raw_title = it.findtext("title", "") or ""
        title = _clean_title(raw_title)
        if not title:
            continue
        if _NOISE.search(title):
            continue  # stock-quote pages / lawsuit spam
        if want_keywords and not _BDC_KEYWORDS.search(raw_title):
            continue
        if aliases and not any(a.lower() in raw_title.lower() for a in aliases):
            continue
        iso, ts = _parse_date(it.findtext("pubDate", "") or "")
        out.append({
            "title": title,
            "url": (it.findtext("link", "") or "").strip(),
            "source": disp,
            "published": it.findtext("pubDate", "") or "",
            "published_iso": iso,
            "_ts": ts,
        })
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    items: dict[str, dict] = {}

    def add(rows, tickers, category):
        for r in rows:
            k = _norm_key(r["title"])
            if not k:
                continue
            if k in items:
                merged = set(items[k].get("tickers", []))
                merged.update(tickers)
                items[k]["tickers"] = sorted(merged)
                continue
            r = dict(r)
            r["tickers"] = sorted(set(tickers))
            r["category"] = category
            items[k] = r

    print("Fetching general BDC / private-credit news (Bloomberg, FT, WSJ)...")
    for q in GENERAL_QUERIES:
        rows = fetch_query(f"{q} {_DOMAIN_CLAUSE}", want_keywords=True, aliases=None)
        print(f"  '{q[:45]}' -> {len(rows)} kept")
        add(rows, [], "general")
        time.sleep(1.0)

    print("Fetching per-BDC news...")
    for tkr, (name, aliases) in BDCS.items():
        rows = fetch_query(f'"{name}" {_DOMAIN_CLAUSE}', want_keywords=False, aliases=aliases)
        if rows:
            print(f"  {tkr:<6} -> {len(rows)} kept")
        add(rows, [tkr], "company")
        time.sleep(0.8)

    all_items = sorted(items.values(), key=lambda r: r.get("_ts", 0), reverse=True)
    for r in all_items:
        r.pop("_ts", None)

    payload = {
        # Live one-shot fetcher (not a resumable build), so a wall-clock
        # stamp here is fine and drives the "refreshed …" footer on the page.
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "sources": list(SOURCES.keys()),
        "items": all_items,
    }
    out_path = SCRIPT_DIR / "news.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    n_company = sum(1 for r in all_items if r["category"] == "company")
    n_general = sum(1 for r in all_items if r["category"] == "general")
    print(f"\nWrote {out_path.name}: {len(all_items)} items "
          f"({n_general} general, {n_company} company-tagged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
