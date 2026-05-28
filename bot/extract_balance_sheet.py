"""Extract Q1 2026 balance-sheet facts for each BDC via the SEC XBRL
company-facts API and write a JSON map → bs_q1.json.

For each BDC, we pull (as of period_end 2026-03-31, form 10-Q):
  - total_liabilities (us-gaap:Liabilities)
  - gross_debt        (us-gaap:LongTermDebt + us-gaap:DebtCurrent or
                       us-gaap:LongTermDebtAndCapitalLeaseObligations)
  - nav               (us-gaap:StockholdersEquity)
  - shares            (us-gaap:CommonStockSharesOutstanding or
                       dei:EntityCommonStockSharesOutstanding)
  - portfolio_fv      (us-gaap:InvestmentOwnedAtFairValue total)
  - nav_per_share     = nav / shares

PSEC has a June 30 fiscal year; their "Q1 calendar" = Q3 fiscal-year, so
the period_end is still 2026-03-31. Handled the same way.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
UA = "BDC Researcher contact@example.com"


def fetch_facts(cik: str) -> dict:
    """Fetch company-facts JSON. Cached on disk."""
    cache_path = SCRIPT_DIR / ".cache" / f"facts_{int(cik):010d}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def latest_value(facts: dict, concept: str, period_end: str,
                 unit_filter: str = "USD") -> float | None:
    """Return the latest reported value for `concept` with end == period_end,
    preferring the most recently filed entry (highest 'filed' date)."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})
    container = gaap.get(concept) or dei.get(concept)
    if not container:
        return None
    units = container.get("units", {})
    for unit, vals in units.items():
        if unit_filter and unit_filter not in unit:
            continue
        matching = [v for v in vals if v.get("end") == period_end]
        if matching:
            # Prefer most recently filed
            matching.sort(key=lambda v: v.get("filed", ""), reverse=True)
            return matching[0].get("val")
    return None


def extract_bs(cik: str, period_end: str) -> dict:
    """Pull balance-sheet facts for a single BDC."""
    try:
        facts = fetch_facts(cik)
    except Exception as e:
        return {"error": f"fetch failed: {e}"}

    out: dict = {"period_end": period_end}

    # Total liabilities
    out["total_liabilities"] = latest_value(facts, "Liabilities", period_end)

    # Gross debt — try a few possible concepts (filers vary)
    debt_concepts = [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "DebtLongtermAndShorttermCombinedAmount",
        "DebtInstrumentCarryingAmount",
    ]
    for c in debt_concepts:
        v = latest_value(facts, c, period_end)
        if v:
            out["gross_debt"] = v
            out["gross_debt_concept"] = c
            break
    # Fallback: short-term + long-term
    if "gross_debt" not in out:
        st = latest_value(facts, "DebtCurrent", period_end) or 0
        lt = latest_value(facts, "LongTermDebtNoncurrent", period_end) or 0
        if st + lt > 0:
            out["gross_debt"] = st + lt
            out["gross_debt_concept"] = "DebtCurrent + LongTermDebtNoncurrent"

    # NAV (stockholders equity / net assets)
    nav_concepts = [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "NetAssetsAttributableToInvestors",
    ]
    for c in nav_concepts:
        v = latest_value(facts, c, period_end)
        if v:
            out["nav"] = v
            out["nav_concept"] = c
            break

    # Shares outstanding
    shares_concepts = [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ]
    for c in shares_concepts:
        v = latest_value(facts, c, period_end, unit_filter="shares")
        if v:
            out["shares"] = v
            out["shares_concept"] = c
            break
    # The dei version is often as-of-filing not as-of-period; if missing,
    # try with a more recent date close to the period_end (~30-60 days
    # later for the 10-Q filing date).
    if "shares" not in out:
        dei_shares = facts.get("facts", {}).get("dei", {}).get(
            "EntityCommonStockSharesOutstanding", {}).get("units", {})
        if dei_shares:
            for unit, vals in dei_shares.items():
                # Find any entry filed shortly after period_end
                relevant = [v for v in vals if v.get("end", "") >= period_end]
                relevant.sort(key=lambda v: v.get("end", ""))
                if relevant:
                    out["shares"] = relevant[0].get("val")
                    out["shares_concept"] = "EntityCommonStockSharesOutstanding (filing date)"
                    break

    # Portfolio FV — for cross-check against extracted SOI totals
    out["portfolio_fv"] = latest_value(
        facts, "InvestmentOwnedAtFairValue", period_end)

    # Derived
    if out.get("nav") and out.get("shares"):
        out["nav_per_share"] = round(out["nav"] / out["shares"], 4)

    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    registry = json.loads(
        (SCRIPT_DIR / "bdc_registry.json").read_text(encoding="utf-8"))

    period_end = "2026-03-31"

    print(f"Pulling Q1 2026 ({period_end}) balance-sheet facts from SEC")
    print(f"{'BDC':5s}  {'Total Liab':>13s}  {'Gross Debt':>13s}  "
          f"{'NAV':>13s}  {'Shares':>13s}  {'NAV/sh':>8s}  notes")
    print("-" * 95)

    out: dict = {}
    for ticker in sorted(registry):
        cik = registry[ticker]["cik"]
        bs = extract_bs(cik, period_end)
        out[ticker] = bs
        if "error" in bs:
            print(f"  {ticker:5s}  ERROR: {bs['error']}")
            continue
        tl = bs.get("total_liabilities")
        gd = bs.get("gross_debt")
        nv = bs.get("nav")
        sh = bs.get("shares")
        nvs = bs.get("nav_per_share")
        notes = ""
        if not gd: notes += "no debt; "
        if not nv: notes += "no NAV; "
        print(
            f"  {ticker:5s}  "
            f"{(tl/1e6 if tl else 0):>11,.0f}M  "
            f"{(gd/1e6 if gd else 0):>11,.0f}M  "
            f"{(nv/1e6 if nv else 0):>11,.0f}M  "
            f"{(sh/1e6 if sh else 0):>11,.1f}M  "
            f"{nvs if nvs else '--':>8}  "
            f"{notes}"
        )
        time.sleep(0.12)

    out_path = SCRIPT_DIR / "bs_q1.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
