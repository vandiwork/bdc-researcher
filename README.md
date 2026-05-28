# BDC Researcher

Cross-BDC portfolio intelligence for 18 publicly-traded Business Development Companies (ARCC, BBDC, BCSF, BXSL, CGBD, FSK, GBDC, GSBD, HTGC, MAIN, MFIC, MSDL, NMFC, OBDC, OCSL, PSEC, TCPC, TSLX).

The site combines SEC XBRL filings (Schedule of Investments, balance sheets) with live Yahoo Finance prices to produce per-BDC dashboards and cross-BDC comparison views.

## Site

When hosted on GitHub Pages, the site is served from `https://<owner>.github.io/<repo>/`. Open `index.html` for navigation.

Pages:
- `dashboards/<ticker>_dashboard.html` — per-BDC portfolio + analytics + pricing simulator
- `comps.html` — cross-BDC comps table with live prices, P/NAV, returns
- `compare.html` — side-by-side comparison
- `pairs.html` — pair-wise overlap analysis
- `markdelta.html` — companies held by multiple BDCs (mark divergence)
- `analytics.html` — cross-BDC analytics
- `overlap.html` — cross-holdings matrix
- `index.html` — landing page

A "Refresh data" button in the footer of every page links to the GitHub Actions UI where the rebuild workflow can be manually triggered.

## Data pipeline

Run from the repo root:

```bash
pip install -r requirements.txt

# 1. Pull SOI XBRL data from SEC EDGAR (per-BDC portfolio positions)
python bot/extract_bdc_soi.py --all --form 10-Q --out bot/out_all

# 2. Cache the SOI HTML (needed for sector / maturity / acq-date enrichment)
python bot/diag_soi_headers.py --form 10-Q

# 3. Join SOI HTML metadata onto XBRL positions + normalize sector/type
python bot/enrich_soi.py

# 4. Pull current-quarter balance sheet (NAV, debt, shares) from XBRL
python bot/extract_balance_sheet.py

# 5. Pull live market data from Yahoo Finance
python bot/extract_market_data.py

# 6. Inject per-BDC data into dashboard HTML files
python bot/build_dashboards.py

# 7. Rebuild cross-BDC site pages (comps, pairs, analytics, etc.)
python bot/build_site_data.py
```

## Hosting / Automation

### One-time setup (after you push this repo to GitHub)

1. **Push to GitHub**:
   ```bash
   git remote add origin https://github.com/<owner>/<repo>.git
   git push -u origin main
   ```

2. **Enable GitHub Pages**:
   - Repo Settings → Pages
   - Source: **GitHub Actions**

3. **Update the repo slug** in `website/assets/refresh-banner.js`:
   ```js
   const REPO_SLUG = "<owner>/<repo>";  // e.g. "vandi/BDC-Scalable"
   ```

4. **Grant Actions write permission** (if not default):
   - Repo Settings → Actions → General → Workflow permissions → "Read and write permissions"

### Workflows

`.github/workflows/refresh-all.yml`
- **Manual trigger**: GitHub Actions tab → "Refresh all data" → "Run workflow". The site's "↻ Refresh data" button links here.
- **Scheduled**: Daily at 23:30 UTC (~6:30 PM ET) Mon-Fri — picks up newly-filed 10-Qs.
- **Pipeline**: runs all 7 steps above, commits regenerated data back to the repo, redeploys Pages.
- **Runtime**: ~10-15 min for a full rebuild.

`.github/workflows/refresh-market.yml`
- **Scheduled**: every 15 min between 13:00-20:59 UTC Mon-Fri (US market hours including DST/non-DST window).
- **Pipeline**: only re-pulls Yahoo Finance + rebuilds cross-BDC pages — skips the slow SOI extraction.
- **Runtime**: ~1-2 min per run.

### What the freshness banner shows

Bottom-right of every page:
- "Filings · X min ago" — when `refresh-all` last ran (full pipeline including SEC filings)
- "Prices · X min ago" — when `refresh-market` last ran (Yahoo prices only)
- "↻ Refresh data" — opens the Actions UI for manual full-rebuild trigger

## Architecture

```
SEC EDGAR
  ├── XBRL inline-tagged 10-Q/10-K
  │     └── bot/extract_bdc_soi.py       → bot/out_all/<TICKER>_<acc>.csv
  │     └── bot/extract_balance_sheet.py → bot/bs_q1.json
  └── HTML 10-Q/10-K document
        └── bot/diag_soi_headers.py      → .cache/soi_headers/<TICKER>_<acc>.htm
              └── bot/enrich_soi.py      → bot/out_all_enriched/<TICKER>_<acc>.csv

Yahoo Finance API
  └── bot/extract_market_data.py         → bot/market_q1.json

Build step
  └── bot/build_dashboards.py            → website/dashboards/<ticker>_dashboard.html
  └── bot/build_site_data.py             → website/{analytics,compare,comps,pairs,markdelta}.html
                                          + website/dashboards/data/{portfolio.json, summary.json}
```

## Codebase

```
bot/
├── extract_bdc_soi.py         # XBRL SOI extractor (per-BDC modules in bot/bdcs/)
├── extract_balance_sheet.py   # XBRL balance sheet (NAV, debt, shares)
├── extract_market_data.py     # Yahoo Finance prices, returns, yields
├── enrich_soi.py              # SOI HTML enrichment + normalization
├── diag_soi_headers.py        # Cache SOI HTML files
├── normalize.py               # GICS sector + canonical security type maps
├── build_dashboards.py        # Inject data into per-BDC HTML
├── build_site_data.py         # Inject data into cross-BDC HTML
├── audit_data.py              # QA: scan for extraction bugs
├── summary_taxonomy.py        # Aggregate breakdown report
├── bdc_registry.json          # Ticker → CIK + name map
├── bdcs/                      # Per-BDC XBRL handlers (parse_identifier overrides)
└── soi_html/                  # Per-BDC HTML parsers

website/
├── *.html                     # Top-level pages (analytics, comps, etc.)
├── dashboards/
│   ├── <ticker>_dashboard.html  # Per-BDC pages (22 tickers)
│   └── data/
│       ├── portfolio.json       # All positions across all BDCs
│       ├── summary.json         # Per-BDC + aggregate sector/type totals
│       └── build_info.json      # Last-refreshed timestamps (CI-written)
├── assets/
│   └── refresh-banner.js      # Freshness banner + Refresh button
└── assets.css

.github/workflows/
├── refresh-all.yml            # Daily + manual full rebuild
└── refresh-market.yml         # 15-min intraday market refresh
```

## License

Internal use only.
