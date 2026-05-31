"""Rebuild the home page (index.html) BDC universe table + the dashboard
landing page (dashboards.html) BDC tiles from latest data sources:
  - bot/bs_q1.json (NAV, debt, shares)
  - bot/market_q1.json (price, return, div yield)
  - bot/out_all_enriched/<TICKER>_*.csv (FV, position metadata)

Also applies the home-page text fixes (Pair Compare → BDC Compare card,
22×22 → 18×18 wording) and adds a # column to the universe table.

Idempotent: re-running just overwrites the data + sortable table.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
WEBSITE = PROJECT_ROOT / "website"

# Full BDC names used by the home table
BDC_NAMES = {
    "ARCC":  "Ares Capital Corporation",
    "BBDC":  "Barings BDC",
    "BCRED": "Blackstone Private Credit Fund",
    "BCSF":  "Bain Capital Specialty Finance",
    "BXSL":  "Blackstone Secured Lending",
    "CGBD":  "Carlyle Secured Lending",
    "FSK":   "FS KKR Capital Corp",
    "GBDC":  "Golub Capital BDC",
    "GSBD":  "Goldman Sachs BDC",
    "HTGC":  "Hercules Capital",
    "MAIN":  "Main Street Capital",
    "MFIC":  "MidCap Financial Investment",
    "MSDL":  "Morgan Stanley Direct Lending",
    "NMFC":  "New Mountain Finance",
    "OBDC":  "Blue Owl Capital Corporation",
    "OCSL":  "Oaktree Specialty Lending",
    "PSEC":  "Prospect Capital",
    "TCPC":  "BlackRock TCP Capital",
    "TSLX":  "Sixth Street Specialty Lending",
}

# Order to display: by FV (desc); we'll sort dynamically at render time too


def _fnum(s) -> float:
    try:
        return float(s or 0)
    except (TypeError, ValueError):
        return 0.0


def load_extracted_fv() -> dict[str, dict]:
    """Per-BDC totals from enriched CSV."""
    out = {}
    for fp in sorted((SCRIPT_DIR / "out_all_enriched").glob("*.csv")):
        ticker = fp.name.split("_")[0]
        if ticker not in BDC_NAMES:
            continue
        with fp.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        fv = sum(_fnum(r.get("fv")) for r in rows)
        positions = sum(1 for r in rows if _fnum(r.get("fv")) != 0)
        out[ticker] = {"fv_m": round(fv / 1e6, 1), "positions": positions}
    return out


def load_bs() -> dict:
    p = SCRIPT_DIR / "bs_q1.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_market() -> dict:
    p = SCRIPT_DIR / "market_q1.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_universe_rows() -> list[dict]:
    """One row per tracked BDC, sorted by FV desc."""
    fv = load_extracted_fv()
    bs = load_bs()
    mk = load_market()
    rows = []
    for t in BDC_NAMES:
        if t not in fv:
            continue
        nav_m = (bs.get(t, {}).get("nav") or 0) / 1e6
        debt_m = (bs.get(t, {}).get("gross_debt") or 0) / 1e6
        nps = bs.get(t, {}).get("nav_per_share")
        price = mk.get(t, {}).get("price")
        div_y = mk.get(t, {}).get("div_yield_pct")
        p_nav = round(price / nps, 2) if (price and nps) else None
        # Headline Portfolio FV = filer's reported InvestmentOwnedAtFairValue
        # (authoritative). A couple of filers (FSK, MSDL) over-tag at the
        # per-position level vs their own reported total; using the reported
        # figure keeps the headline correct while per-position data stays
        # faithful for the analytical tabs. No-op for the ~17 BDCs whose
        # extracted sum already matches reported.
        reported_fv = bs.get(t, {}).get("portfolio_fv")
        fv_m = round(reported_fv / 1e6, 1) if reported_fv else fv[t]["fv_m"]
        rows.append({
            "ticker": t,
            "name": BDC_NAMES[t],
            "fv_m": fv_m,
            "positions": fv[t]["positions"],
            "nav_m": round(nav_m),
            "debt_m": round(debt_m),
            "nav_per_share": nps,
            "price": price,
            "p_nav": p_nav,
            "div_yield_pct": div_y,
        })
    rows.sort(key=lambda r: -r["fv_m"])
    return rows


# ── index.html universe table ────────────────────────────────────────


def _fmt_num(v) -> str:
    if v is None:
        return "&mdash;"
    if abs(v) >= 1000:
        return f"{round(v):,}"
    return f"{v:.1f}"


def _fmt_pnav(v) -> str:
    if v is None:
        return '<span class="num">&mdash;</span>'
    cls = "pnav-lo" if v < 1 else "pnav-hi"
    return f'<span class="num {cls}">{v:.2f}x</span>'


def render_universe_table_body(rows: list[dict]) -> str:
    """The <tbody> contents for index.html's universe table."""
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append(
            f'<tr>'
            f'<td class="num">{i}</td>'
            f'<td><a href="dashboards/{r["ticker"].lower()}_dashboard.html">{r["ticker"]}</a></td>'
            f'<td>{r["name"]}</td>'
            f'<td class="num">${r["price"]:.2f}</td>' if r["price"] is not None else '<td class="num">&mdash;</td>'
        )
        # Easier to build piece by piece
    # The above mixing-and-matching is fragile; rebuild cleanly:
    out = []
    for i, r in enumerate(rows, 1):
        price_str = f'${r["price"]:.2f}' if r["price"] is not None else "&mdash;"
        div_str = f'{r["div_yield_pct"]:.1f}%' if r["div_yield_pct"] is not None else "&mdash;"
        out.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f'<td><a href="dashboards/{r["ticker"].lower()}_dashboard.html">{r["ticker"]}</a></td>'
            f'<td>{r["name"]}</td>'
            f'<td class="num">{price_str}</td>'
            f'<td class="num">{_fmt_pnav(r["p_nav"])[5:]}'   # strip <span> wrapper duplicate
            f'<td class="num">{r["fv_m"]:,.0f}</td>'
            f'<td class="num">{r["nav_m"]:,}</td>'
            f'<td class="num">{div_str}</td>'
            "</tr>"
        )
    return "\n".join(out)


def _build_tbody_html(rows: list[dict]) -> str:
    parts = []
    for i, r in enumerate(rows, 1):
        price_str = f'${r["price"]:.2f}' if r["price"] is not None else "&mdash;"
        div_str = f'{r["div_yield_pct"]:.1f}%' if r["div_yield_pct"] is not None else "&mdash;"
        if r["p_nav"] is None:
            pnav_cell = '<td class="num">&mdash;</td>'
        else:
            cls = "pnav-lo" if r["p_nav"] < 1 else "pnav-hi"
            pnav_cell = f'<td class="num {cls}">{r["p_nav"]:.2f}x</td>'
        parts.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f'<td><a href="dashboards/{r["ticker"].lower()}_dashboard.html">{r["ticker"]}</a></td>'
            f'<td>{r["name"]}</td>'
            f'<td class="num">{price_str}</td>'
            f'{pnav_cell}'
            f'<td class="num">{r["fv_m"]:,.0f}</td>'
            f'<td class="num">{r["nav_m"]:,}</td>'
            f'<td class="num">{div_str}</td>'
            "</tr>"
        )
    return "\n".join(parts)


def update_index_html(rows: list[dict]) -> bool:
    fp = WEBSITE / "index.html"
    if not fp.exists():
        return False
    content = fp.read_text(encoding="utf-8")

    # 1. Replace the "Pair Compare" card with "BDC Compare"
    content = re.sub(
        r'<a class="bdccard" href="pairs\.html">\s*'
        r'<div class="tkr">[^<]*Pair Compare[^<]*</div>\s*'
        r'<div class="nm">[^<]*</div>\s*</a>',
        '<a class="bdccard" href="compare.html">\n'
        '    <div class="tkr">⇄ BDC Compare</div>\n'
        '    <div class="nm">Side-by-side KPIs, sector / type / maturity breakouts, '
        f'and pair-compare on shared borrowers across all {len(rows)} BDCs.</div>\n'
        '  </a>',
        content, flags=re.S)

    # 1b. Refresh the top KPI stats
    total_fv_b = sum(r["fv_m"] for r in rows) / 1000
    total_positions = sum(r["positions"] for r in rows)
    new_stats = (
        '<div class="stats">\n'
        f'  <div class="stat"><div class="lab">BDCs Tracked</div><div class="val">{len(rows)}</div></div>\n'
        f'  <div class="stat"><div class="lab">Total Portfolio FV</div><div class="val">${total_fv_b:,.1f}B</div></div>\n'
        f'  <div class="stat"><div class="lab">Total Positions</div><div class="val">{total_positions:,}</div></div>\n'
        f'  <div class="stat"><div class="lab">Filing Period</div><div class="val">Q1 2026</div></div>\n'
        '</div>'
    )
    # Replace the entire stats block up to the next grid div, including
    # any orphaned <div class="stat"> lines from prior builds.
    content = re.sub(
        r'<div class="stats">.*?(?=<div class="grid)',
        lambda _: new_stats + "\n\n",
        content, count=1, flags=re.S)

    # 2. Cross-Holdings card matrix dimension + page subtitle — keep the BDC
    # count in sync with the actual number of tracked funds (no hardcoding).
    n = len(rows)
    content = re.sub(r"\d+×\d+ matrix", f"{n}×{n} matrix", content)
    content = re.sub(r"\d+ Business Development Companies",
                     f"{n} Business Development Companies", content)
    content = re.sub(r"across all \d+ BDCs", f"across all {n} BDCs", content)

    # 3. Replace the universe-table header row + tbody
    new_thead = (
        '<thead><tr>\n'
        '<th class="num">#</th>\n'
        '<th>Ticker</th>\n'
        '<th>Name</th>\n'
        '<th class="num">Price</th>\n'
        '<th class="num">P/NAV</th>\n'
        '<th class="num">Portfolio FV ($M)</th>\n'
        '<th class="num">NAV ($M)</th>\n'
        '<th class="num">Div Yield</th>\n'
        '</tr></thead>'
    )
    content = re.sub(
        r'<thead><tr>.*?</tr></thead>',
        new_thead, content, count=1, flags=re.S)

    new_tbody_html = (
        '<tbody id="bdc-body">\n'
        + _build_tbody_html(rows) +
        '\n</tbody>'
    )
    content = re.sub(
        r'<tbody id="bdc-body">.*?</tbody>',
        new_tbody_html, content, count=1, flags=re.S)

    # 4. The sortable-table JS sorts by column index. The new # column
    # is at index 0; default sort should still be by FV (column 5).
    content = re.sub(
        r'let sortK = \d+, sortDir = -1;',
        'let sortK = 5, sortDir = -1;',
        content, count=1)

    # 5. Renumber the # column after each sort so 1..N stays in display order
    if 'function renumberIndex' not in content:
        # Inject a small helper that updates the leading # cell after sort
        inject = (
            "function renumberIndex(){\n"
            "  document.querySelectorAll('#bdc-body tr').forEach((tr, i) => {\n"
            "    if (tr.cells[0]) tr.cells[0].textContent = (i + 1);\n"
            "  });\n"
            "}\n"
        )
        content = content.replace(
            "function doSort(){",
            inject + "function doSort(){"
        )
        # Call renumberIndex after each sort
        content = content.replace(
            "rows.forEach(r => tbody.appendChild(r));",
            "rows.forEach(r => tbody.appendChild(r));\n    renumberIndex();"
        )

    fp.write_text(content, encoding="utf-8")
    return True


# ── dashboards.html — refresh BDC tiles with live data ───────────────


def update_dashboards_html(rows: list[dict]) -> bool:
    fp = WEBSITE / "dashboards.html"
    if not fp.exists():
        return False
    content = fp.read_text(encoding="utf-8")

    # Find the BDC tile grid and rebuild it
    bs = load_bs()

    # Each card matches the existing `<div class="grid grid-3">` layout
    # — ticker + name + 4 metric rows (P/NAV, Portfolio FV, Div Yield,
    # Data as of).
    tile_html = []
    # Dashboard tiles are ordered alphabetically by ticker (the index.html
    # universe table stays FV-sorted).
    for r in sorted(rows, key=lambda x: x["ticker"]):
        period = bs.get(r["ticker"], {}).get("period_end", "—")
        div_str = (f'{r["div_yield_pct"]:.1f}%'
                   if r["div_yield_pct"] is not None else "—")
        pnav_str = f'{r["p_nav"]:.2f}x' if r["p_nav"] is not None else "—"
        pnav_cls = ("pnav-lo" if r["p_nav"] and r["p_nav"] < 1
                    else "pnav-hi" if r["p_nav"] else "")
        fv_str = f"${r['fv_m']/1000:,.1f}B" if r["fv_m"] >= 1000 else f"${r['fv_m']:,.0f}M"
        tile_html.append(
            f'<a class="bdccard" href="dashboards/{r["ticker"].lower()}_dashboard.html">\n'
            f'  <div class="tkr">{r["ticker"]}</div>\n'
            f'  <div class="nm">{r["name"]}</div>\n'
            f'  <div class="row"><span class="l">P/NAV</span>'
            f'<span class="v {pnav_cls}">{pnav_str}</span></div>\n'
            f'  <div class="row"><span class="l">Portfolio FV</span>'
            f'<span class="v">{fv_str}</span></div>\n'
            f'  <div class="row"><span class="l">Div Yield</span>'
            f'<span class="v">{div_str}</span></div>\n'
            f'  <div class="row"><span class="l">Data as of</span>'
            f'<span class="v" style="font-size:11px">{period}</span></div>\n'
            f'</a>'
        )

    new_grid = (
        '<div class="grid grid-3">\n' + "\n".join(tile_html) + '\n</div>'
    )
    new_content, n = re.subn(
        r'<div class="grid grid-3">.*?</div>\s*</div>',
        lambda _: new_grid + "\n</div>",
        content, count=1, flags=re.S)
    if n == 0:
        return False
    fp.write_text(new_content, encoding="utf-8")
    return True


# ── Main ─────────────────────────────────────────────────────────────


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    rows = build_universe_rows()
    print(f"Built universe: {len(rows)} BDCs")
    ok1 = update_index_html(rows)
    print(f"  index.html      {'OK' if ok1 else 'SKIP'}")
    ok2 = update_dashboards_html(rows)
    print(f"  dashboards.html {'OK' if ok2 else 'SKIP'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
