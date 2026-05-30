"""Full data-integrity audit. Compares our extracted/stored figures
against the filer's reported XBRL facts for every BDC."""
import sys, json, time, csv, re
sys.stdout.reconfigure(encoding="utf-8")
import urllib.request as ur
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent
reg = json.loads((SCRIPT / "bdc_registry.json").read_text())
bs = json.loads((SCRIPT / "bs_q1.json").read_text())
mkt = json.loads((SCRIPT / "market_q1.json").read_text())

_cache = {}
def facts_for(cik):
    if cik in _cache:
        return _cache[cik]
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = ur.Request(url, headers={"User-Agent": "BDC researcher contact@example.com"})
    cf = json.loads(ur.urlopen(req, timeout=45).read())
    _cache[cik] = cf
    time.sleep(0.12)
    return cf

def latest(gaap, tag, period, unit=None):
    if tag not in gaap:
        return None
    best = None
    for uk, vals in gaap[tag].get("units", {}).items():
        if unit and uk != unit:
            continue
        for v in vals:
            if v.get("end") == period and v.get("form", "").startswith("10-Q"):
                if best is None or abs(v["val"]) > abs(best):
                    best = v["val"]
    return best

from extract_bdc_soi import fv_usd  # FX-aware USD conversion

def extracted_fv(ticker):
    fs = sorted((SCRIPT / "out_all").glob(f"{ticker}_*.csv"),
                key=lambda p: p.stem.split("_", 1)[1], reverse=True)
    if not fs:
        return None, 0
    with fs[0].open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # CSV stores native-currency FV; convert to USD for the total (mirrors
    # the extractor's summary logic) so foreign holdings aren't overcounted.
    tot = sum(fv_usd(float(r.get("fv") or 0), (r.get("ccy") or "USD")) for r in rows)
    return tot, len(rows)

def pct(a, b):
    return (a - b) / b * 100 if b else float("nan")

print("="*92)
print("AUDIT 1 — PORTFOLIO FV: extracted vs reported XBRL InvestmentOwnedAtFairValue")
print("="*92)
print(f'{"BDC":<6} {"PERIOD":<11} {"EXTRACTED":>13} {"REPORTED":>13} {"DELTA%":>8} {"POS":>5}  FLAG')
fv_issues = []
for t in sorted(reg):
    cik = reg[t]["cik"]
    try:
        cf = facts_for(cik)
    except Exception as e:
        print(f"{t:<6} ERROR {e}"); continue
    gaap = cf.get("facts", {}).get("us-gaap", {})
    period = bs.get(t, {}).get("period_end") or "2026-03-31"
    rep = latest(gaap, "InvestmentOwnedAtFairValue", period)
    ext, npos = extracted_fv(t)
    if rep and ext:
        d = pct(ext, rep)
        flag = "" if abs(d) < 1 else ("  <<< >1%" if abs(d) < 5 else "  <<<<< >5%")
        if abs(d) >= 1: fv_issues.append((t, round(d, 2)))
        print(f"{t:<6} {period:<11} {ext/1e6:>12,.1f}M {rep/1e6:>12,.1f}M {d:>+7.2f}% {npos:>5}{flag}")
    else:
        print(f"{t:<6} {period:<11}  ext={ext}  rep={rep}  (missing)")

print()
print("="*92)
print("AUDIT 2 — BALANCE SHEET: stored vs reported XBRL")
print("="*92)
print(f'{"BDC":<6} {"NAV":>10} {"GAV(Assets)":>12} {"Liab":>10} {"Debt":>10} {"Shares(M)":>10}  FLAGS')
bs_issues = []
for t in sorted(reg):
    if t not in bs:
        print(f"{t:<6} (not in bs_q1.json)"); bs_issues.append((t, "missing")); continue
    cik = reg[t]["cik"]
    period = bs[t]["period_end"]
    try:
        cf = facts_for(cik)
    except Exception as e:
        print(f"{t:<6} ERROR {e}"); continue
    gaap = cf.get("facts", {}).get("us-gaap", {})
    checks = []
    # NAV
    rep_nav = latest(gaap, "StockholdersEquity", period) or latest(gaap, "NetAssets", period)
    our_nav = bs[t].get("nav")
    if rep_nav and our_nav and abs(pct(our_nav, rep_nav)) > 0.5:
        checks.append(f"NAV {pct(our_nav,rep_nav):+.1f}%")
    # GAV / total assets
    rep_assets = latest(gaap, "Assets", period)
    our_assets = bs[t].get("total_assets")
    if rep_assets and our_assets and abs(pct(our_assets, rep_assets)) > 0.5:
        checks.append(f"GAV {pct(our_assets,rep_assets):+.1f}%")
    if rep_assets and not our_assets:
        checks.append("GAV missing")
    # Liabilities
    rep_liab = latest(gaap, "Liabilities", period)
    our_liab = bs[t].get("total_liabilities")
    if rep_liab and our_liab and abs(pct(our_liab, rep_liab)) > 0.5:
        checks.append(f"Liab {pct(our_liab,rep_liab):+.1f}%")
    sh = bs[t].get("shares") or 0
    flags = "  ".join(checks) if checks else "OK"
    if checks: bs_issues.append((t, flags))
    print(f"{t:<6} {(our_nav or 0)/1e6:>9,.0f}M {(our_assets or 0)/1e6:>11,.0f}M "
          f"{(our_liab or 0)/1e6:>9,.0f}M {(bs[t].get('gross_debt') or 0)/1e6:>9,.0f}M "
          f"{sh/1e6:>10,.1f}  {flags}")

print()
print("="*92)
print("AUDIT 3 — MARKET DATA sanity (price, P/NAV, div yield)")
print("="*92)
print(f'{"BDC":<6} {"PRICE":>9} {"P/NAV":>7} {"DIV%":>7}  FLAGS')
mkt_issues = []
for t in sorted(reg):
    m = mkt.get(t, {})
    if m.get("error"):
        print(f"{t:<6} {'—':>9} {'—':>7} {'—':>7}  no market data ({m['error']})")
        continue
    price = m.get("price")
    nps = bs.get(t, {}).get("nav_per_share")
    pnav = price / nps if (price and nps) else None
    dy = m.get("div_yield_pct")
    checks = []
    if pnav and (pnav < 0.2 or pnav > 2.5): checks.append(f"P/NAV={pnav:.2f} suspicious")
    if dy and (dy < 0 or dy > 25): checks.append(f"DivY={dy:.1f}% suspicious")
    if price and price <= 0: checks.append("price<=0")
    if checks: mkt_issues.append((t, checks))
    print(f"{t:<6} {('$%.2f'%price) if price else '—':>9} "
          f"{('%.2fx'%pnav) if pnav else '—':>7} {('%.1f%%'%dy) if dy else '—':>7}  "
          f"{'  '.join(checks) if checks else 'OK'}")

print()
print("="*92)
print("SUMMARY OF ISSUES")
print("="*92)
print(f"FV  >1% delta: {fv_issues or 'none'}")
print(f"BS  anomalies: {bs_issues or 'none'}")
print(f"MKT anomalies: {mkt_issues or 'none'}")
