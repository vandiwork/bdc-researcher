"""Diagnostic: for each BDC, find the filer-canonical portfolio FV from
the un-segmented XBRL fact. This is the authoritative target our extractor
should match. Also pulls Affiliated breakdown (Unaffiliated / Affiliated-
Noncontrolled / Affiliated-Controlled) for sanity checks.

Run:  python diag_canonical.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

import requests
from lxml import etree

SCRIPT_DIR = Path(__file__).resolve().parent
UA = "BDC Researcher contact@example.com"
NS_XBRLI = "http://www.xbrl.org/2003/instance"
NS_XBRLDI = "http://xbrl.org/2006/xbrldi"

AFFIL_LABELS = {
    "us-gaap:InvestmentUnaffiliatedIssuerMember": "Unaffiliated",
    "us-gaap:InvestmentAffiliatedIssuerNoncontrolledMember": "Affiliated-NC",
    "us-gaap:InvestmentAffiliatedIssuerControlledMember": "Affiliated-Ctrl",
    "us-gaap:InvestmentAffiliatedIssuerMember": "Affiliated",
}


def find_latest_10k(cik: str, sess):
    sess.headers["Host"] = "data.sec.gov"
    try:
        r = sess.get(
            f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
            timeout=30)
        r.raise_for_status()
    finally:
        sess.headers.pop("Host", None)
    rec = r.json()["filings"]["recent"]
    for i, f in enumerate(rec["form"]):
        if f == "10-K":
            return {
                "accession": rec["accessionNumber"][i],
                "primary": rec["primaryDocument"][i],
                "period": rec["reportDate"][i],
            }
    return None


def find_xbrl_url(cik: str, accession_raw: str, primary: str,
                  sess) -> str | None:
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_raw}"
    if primary.endswith(".htm"):
        url = f"{base}/{primary[:-4]}_htm.xml"
        if sess.head(url, timeout=20).status_code == 200:
            return url
    idx = sess.get(base + "/", timeout=30).text
    m = re.search(r'href="([^"]+_htm\.xml)"', idx)
    if not m:
        return None
    href = m.group(1)
    if href.startswith("/"):
        return f"https://www.sec.gov{href}"
    return f"{base}/{href}"


def analyze(ticker: str, cik: str, sess) -> dict:
    info = find_latest_10k(cik, sess)
    if not info:
        return {"ticker": ticker, "error": "no 10-K"}
    raw = info["accession"].replace("-", "")
    xml_url = find_xbrl_url(cik, raw, info["primary"], sess)
    if not xml_url:
        return {"ticker": ticker, "error": "no XBRL"}

    r = sess.get(xml_url, timeout=180)
    r.raise_for_status()
    xml = r.content

    root = etree.fromstring(xml)
    # Build context map: cid -> (period_end, dims, has_identifier_axis)
    contexts: dict[str, dict] = {}
    for ctx in root.findall(f"{{{NS_XBRLI}}}context"):
        cid = ctx.get("id", "")
        instant = ctx.find(f"{{{NS_XBRLI}}}period/{{{NS_XBRLI}}}instant")
        pend = instant.text if instant is not None else ""
        dims = {}
        has_ident = False
        seg = ctx.find(f"{{{NS_XBRLI}}}entity/{{{NS_XBRLI}}}segment")
        if seg is not None:
            for mem in seg.findall(f"{{{NS_XBRLDI}}}explicitMember"):
                d = mem.get("dimension", "")
                dims[d] = (mem.text or "").strip()
            for tym in seg.findall(f"{{{NS_XBRLDI}}}typedMember"):
                d = tym.get("dimension", "")
                if d.endswith("InvestmentIdentifierAxis"):
                    has_ident = True
                children = list(tym)
                v = (children[0].text if children else "") or ""
                dims[d] = v
        contexts[cid] = {
            "pend": pend, "dims": dims, "has_ident": has_ident,
            "n_dims": len(dims),
        }

    # Walk facts: tally InvestmentOwnedAtFairValue by context type.
    # Filers commonly tag the same total multiple times with different
    # `decimals` precision (balance sheet, financial highlights, etc.).
    # Dedupe by (contextRef, rounded-value) so we don't double-count.
    period = info["period"]
    totals = {
        "unsegmented": 0.0,
        "affil_only": {},
        "by_segment_count": {},
        "n_position_facts": 0,
        "position_fv_sum": 0.0,
        "non_position_fv_sum": 0.0,
    }
    seen: set[tuple[str, int]] = set()
    for el in root.iter():
        qn = etree.QName(el)
        if qn.localname != "InvestmentOwnedAtFairValue":
            continue
        cref = el.get("contextRef") or ""
        ctx = contexts.get(cref)
        if not ctx:
            continue
        if ctx["pend"] != period:
            continue
        try:
            v = float((el.text or "").strip())
        except ValueError:
            continue
        key = (cref, round(v / 1000.0))   # round to nearest $K
        if key in seen:
            continue
        seen.add(key)
        n_dims = ctx["n_dims"]
        totals["by_segment_count"][n_dims] = (
            totals["by_segment_count"].get(n_dims, 0.0) + v)
        if n_dims == 0:
            totals["unsegmented"] += v
        if (n_dims == 1
                and "us-gaap:InvestmentIssuerAffiliationAxis" in ctx["dims"]):
            mem = ctx["dims"]["us-gaap:InvestmentIssuerAffiliationAxis"]
            label = AFFIL_LABELS.get(mem, mem)
            totals["affil_only"][label] = totals["affil_only"].get(label, 0.0) + v
        if ctx["has_ident"]:
            totals["n_position_facts"] += 1
            totals["position_fv_sum"] += v
        else:
            totals["non_position_fv_sum"] += v

    return {
        "ticker": ticker,
        "cik": cik,
        "accession": info["accession"],
        "period": period,
        "xml_url": xml_url,
        "totals": totals,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    registry = json.loads((SCRIPT_DIR / "bdc_registry.json").read_text())
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})

    rows = []
    print(f"{'TICKER':<7s} {'CANONICAL FV':>16s} {'AFFIL SUM':>16s} {'POS-FV':>16s} {'NON-POS':>14s} {'POS#':>6s}")
    print("-" * 90)
    for t, info in registry.items():
        cik = info["cik"]
        try:
            a = analyze(t, cik, sess)
        except Exception as e:
            print(f"{t:<7s} ERROR: {type(e).__name__}: {e}")
            continue
        if a.get("error"):
            print(f"{t:<7s} ERROR: {a['error']}")
            continue
        tot = a["totals"]
        canonical = tot["unsegmented"]
        affil = sum(tot["affil_only"].values())
        pos = tot["position_fv_sum"]
        nonpos = tot["non_position_fv_sum"]
        npos = tot["n_position_facts"]
        print(f"{t:<7s} ${canonical/1e6:>13,.1f}M ${affil/1e6:>13,.1f}M ${pos/1e6:>13,.1f}M ${nonpos/1e6:>11,.1f}M {npos:>6d}")
        rows.append({
            "ticker": t, "cik": cik, "period": a["period"],
            "accession": a["accession"],
            "canonical_fv": canonical,
            "affil_sum_fv": affil,
            "position_fv_sum_xbrl": pos,
            "non_position_fv_sum_xbrl": nonpos,
            "n_position_facts": npos,
            "affil_breakdown": json.dumps(tot["affil_only"]),
        })
        time.sleep(0.15)
    out = SCRIPT_DIR / "out_all" / "_canonical.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
