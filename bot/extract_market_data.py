"""Pull current market data for each BDC from Yahoo Finance.

For each ticker, fetches:
  - price            : last close
  - prev_close       : prior trading day close
  - today_pct        : % change vs prev close
  - mtd_pct          : % change since start of current month
  - ytd_pct          : % change since start of year
  - ltm_pct          : trailing 12-month total return (price-only)
  - div_yield        : trailing dividend yield
  - market_cap       : market cap
  - week52_high/low  : 52-week range

Writes bot/market_q1.json.

Used by build_site_data.py to refresh comps.html and pairs.html `pnav`.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

SCRIPT_DIR = Path(__file__).resolve().parent

# All 22 BDCs shown on the website (18 in registry + 4 extras with dashboards)
TICKERS = [
    "ARCC", "BBDC", "BCRED", "BCSF", "BXSL", "CGBD", "FSK", "GBDC",
    "GSBD", "HTGC", "MAIN", "MFIC", "MSDL", "NMFC", "OBDC", "OCSL",
    "PSEC", "SLRC", "TCPC", "TRIN", "TSLX", "WHF",
]


def pct(new: float, old: float) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / old * 100, 2)


def fetch_one(ticker: str) -> dict:
    """Pull market snapshot + returns for one ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="1y", auto_adjust=False)
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

    if hist.empty:
        return {"ticker": ticker, "error": "empty history"}

    closes = hist["Close"]
    price = round(float(closes.iloc[-1]), 4)
    prev = round(float(closes.iloc[-2]), 4) if len(closes) >= 2 else None

    today_dt = hist.index[-1]
    today_str = today_dt.strftime("%Y-%m-%d")

    # MTD: last close of prior month
    month_start = today_dt.replace(day=1)
    prior_month_closes = closes[closes.index < month_start]
    mtd_base = float(prior_month_closes.iloc[-1]) if len(prior_month_closes) else None

    # YTD: last close of prior year
    year_start = today_dt.replace(month=1, day=1)
    prior_year_closes = closes[closes.index < year_start]
    ytd_base = float(prior_year_closes.iloc[-1]) if len(prior_year_closes) else None

    # LTM: first close ~12 months ago in the period window
    ltm_base = float(closes.iloc[0])

    out = {
        "ticker": ticker,
        "as_of": today_str,
        "price": price,
        "prev_close": prev,
        "today_pct": pct(price, prev),
        "mtd_pct": pct(price, mtd_base) if mtd_base else None,
        "ytd_pct": pct(price, ytd_base) if ytd_base else None,
        "ltm_pct": pct(price, ltm_base) if ltm_base else None,
        # yfinance reports dividendYield as a percent (e.g. 10.18 = 10.18%)
        "div_yield_pct": info.get("dividendYield"),
        "market_cap": info.get("marketCap"),
        "week52_high": info.get("fiftyTwoWeekHigh"),
        "week52_low": info.get("fiftyTwoWeekLow"),
        "beta": info.get("beta"),
    }
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print(f"Pulling market data for {len(TICKERS)} BDCs from Yahoo Finance")
    print(f"{'TKR':5s}  {'Price':>8s}  {'Today':>7s}  {'MTD':>7s}  "
          f"{'YTD':>7s}  {'LTM':>7s}  {'Yield':>7s}  {'MktCap':>10s}")
    print("-" * 78)
    out: dict = {}
    for ticker in TICKERS:
        d = fetch_one(ticker)
        out[ticker] = d
        if "error" in d:
            print(f"  {ticker:5s}  ERROR: {d['error']}")
            continue
        mc = d.get("market_cap")
        mc_str = f"${mc/1e9:.1f}B" if mc else "—"
        dy = d.get("div_yield_pct")
        dy_str = f"{dy:.1f}%" if dy else "—"

        def f(p):
            if p is None: return "—"
            return f"{p:+.1f}%"

        print(f"  {ticker:5s}  ${d['price']:>6.2f}  {f(d.get('today_pct')):>7s}  "
              f"{f(d.get('mtd_pct')):>7s}  {f(d.get('ytd_pct')):>7s}  "
              f"{f(d.get('ltm_pct')):>7s}  {dy_str:>7s}  {mc_str:>10s}")
        time.sleep(0.1)

    # Stamp the exact pull time (UTC) so the Comps page can show when prices
    # were last fetched, not just the close date.
    fetched = datetime.now(timezone.utc).isoformat(timespec="minutes")
    for d in out.values():
        d["fetched_utc"] = fetched

    out_path = SCRIPT_DIR / "market_q1.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    as_of = next((d.get("as_of") for d in out.values() if d.get("as_of")), "")
    print(f"\nWrote {out_path}  (as_of: {as_of}, fetched: {fetched})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
