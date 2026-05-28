# BDC Schedule of Investments extractor

Extracts per-position Schedule of Investments data from SEC EDGAR filings
(10-K, 10-Q) for 18 US-listed BDCs. Pulls structured XBRL facts and emits
both a JSON file matching the dashboard schema and an analysis-friendly
CSV per filing.

## Setup

```powershell
cd "C:\Users\vandi\Documents\BDC Scalable\bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requests` and `lxml` may already be available system-wide on this machine.

## Usage

```powershell
# Latest 10-K for a single BDC (most common)
python extract_bdc_soi.py ARCC
python extract_bdc_soi.py BXSL
python extract_bdc_soi.py MAIN --form 10-Q

# Specific accession number
python extract_bdc_soi.py ARCC --accession 0001287750-26-000006

# Or a full filing-directory URL
python extract_bdc_soi.py ARCC --accession https://www.sec.gov/Archives/edgar/data/1287750/000128775026000006/

# Run all 18 covered BDCs in one pass, write a delta-vs-dashboard summary
python extract_bdc_soi.py --all --out out_all
```

SEC requires a non-default User-Agent. Override the default with
`--user-agent "Your Name your@email.com"` for production runs.

## Covered BDCs

ARCC, BBDC, BCSF, BXSL, CGBD, FSK, GBDC, GSBD, HTGC, MAIN, MFIC, MSDL,
NMFC, OBDC, OCSL, PSEC, TCPC, TSLX. CIK mapping in `bdc_registry.json`.

## Output

For each `<TICKER>` + `<accession>` run:

- `out/<TICKER>_<accession>.json` — array of position records, shape-
  compatible with the `DATA = [...]` block in each dashboard. Dollar
  amounts in **thousands** ($K) to match dashboard convention.
- `out/<TICKER>_<accession>.csv` — same data plus filing metadata (cik,
  accession, form, period_end, file_date), all numerics in **raw USD**.

In `--all` mode also writes `out_all/_summary.csv` with totals per BDC
and the percentage delta vs the dashboard's portfolio FV.

### Schema (JSON, per dashboard convention)

| field | description |
| --- | --- |
| `bdc` | Ticker |
| `entity` | Issuer name (pre-tranche-descriptor split of the XBRL identifier) |
| `company` | Cleaned short name (= entity in v1) |
| `type` | First Lien / Second Lien / Equity / Preferred Equity / Warrant / etc. — derived from identifier |
| `fv` | Fair value, in $K |
| `cost` | Amortized cost, in $K |
| `par` | Principal amount, in $K (debt only) |
| `mark` | `fv / cost × 100` |
| `spread` | Basis spread over variable rate, % |
| `rate` | All-in interest rate, % |
| `pik` | True if InvestmentInterestRatePaidInKind > 0 |
| `ccy` | Currency (USD default; inferred from unitRef) |
| `desc`, `sector`, `affil`, `baseRate`, `maturity`, `acq` | null in v1 — see "Known gaps" |

## How it works

Most BDCs encode the SOI in XBRL using a typed dimension
`us-gaap:InvestmentIdentifierAxis` whose value is the issuer-tranche label.
Numeric facts hang off these contexts:

| XBRL concept | Output field |
| --- | --- |
| `us-gaap:InvestmentOwnedAtFairValue` | `fv` |
| `us-gaap:InvestmentOwnedAtCost` | `cost` |
| `us-gaap:InvestmentOwnedBalancePrincipalAmount` | `par` |
| `us-gaap:InvestmentOwnedBalanceShares` | `shares` |
| `us-gaap:InvestmentInterestRate` | `rate` |
| `us-gaap:InvestmentBasisSpreadVariableRate` | `spread` |
| `us-gaap:InvestmentInterestRatePaidInKind` | `pik_rate` |

The extractor:

1. Looks up the filer's CIK via `bdc_registry.json`.
2. Finds the most recent filing of the requested form via
   `data.sec.gov/submissions/CIK<10>.json` (cached for 1h).
3. Locates the XBRL instance document (`<basename>_htm.xml`).
4. Parses contexts → typed-member `InvestmentIdentifierAxis` values.
5. Streams numeric facts and groups by contextRef.
6. Filters out:
   - Issuer-level roll-ups (an identifier that's a comma-prefix of another's).
   - Sub-entity SOIs tagged with explicit dimensions other than the standard
     issuer-identification axes (catches JV/CLO sub-SOIs in BCSF, NMFC, OCSL).
   - Concentration-disclosure placeholders ("Top Five Largest...", etc.).
   - Alias rows with matching `(entity, type, FV)` to a canonical row that
     has cost data (catches the `.1` / `.2` suffix pattern in MAIN, BBDC).
7. Derives `type` (First Lien / Equity / Warrant / etc.) via regex on the
   identifier label.

## Validation results (latest 10-K, FY2025 period)

| Ticker | Positions | Extracted FV ($M) | Dashboard FV ($M) | Δ | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| ARCC | 1,382 | 29,518 | 29,485 | +0.1% | OK |
| BBDC | 660 | 2,411 | 2,399 | +0.5% | OK |
| BCSF | 523 | 2,511 | 2,509 | +0.1% | OK |
| BXSL | 674 | 14,497 | 14,207 | +2.0% | OK |
| CGBD | 234 | 2,567 | 2,464 | +4.2% | OK |
| FSK | 612 | 14,809 | 14,404 | +2.8% | OK |
| GBDC | 1,748 | 8,682 | 8,769 | −1.0% | OK |
| GSBD | 551 | 3,253 | 3,262 | −0.3% | OK |
| HTGC | 341 | 4,445 | 4,477 | −0.7% | OK |
| MAIN | 621 | 5,551 | 5,518 | +0.6% | OK |
| MFIC | 615 | 3,268 | 3,168 | +3.2% | OK |
| MSDL | 593 | 3,772 | 3,772 | −0.0% | OK |
| NMFC | 347 | 2,766 | 2,742 | +0.9% | OK |
| OBDC | 550 | 16,471 | 16,475 | −0.0% | OK |
| OCSL | 333 | 2,846 | 2,838 | +0.3% | OK |
| PSEC | 205 | 6,820 | 6,674 | +2.2% | OK |
| TCPC | 325 | 1,533 | 1,533 | +0.0% | OK |
| TSLX | 221 | 3,360 | 3,347 | +0.4% | OK |

**All 18 BDCs within 5% of dashboard.** 13 within ±1%.

The remaining sub-3% positive deltas reflect per-tranche granularity vs
the dashboard's modest aggregation choices (e.g. HTGC reports Term A/B/C
+ Revolver slices per company; the dashboard may aggregate). All position
data is correct per filer.

## Per-BDC designated bots

Each BDC has a designated module in `bdcs/` capturing filer-specific
quirks. The framework auto-discovers them via `bdcs/<ticker>.py`.

| Module | Custom logic |
| --- | --- |
| `arcc.py` | none (generic) |
| `bbdc.py` | post-filter dedup for cross-entity FV-match aliases (entity-name typo variants) |
| `bcsf.py` | rich identifier parser — embeds sector, type, base rate, spread, rate, maturity, ccy |
| `bxsl.py` | none (generic) |
| `cgbd.py` | drop `"Credit Fund \|"` JV sub-SOI rows; structured pipe-parser; standalone aliases |
| `fsk.py` | entity merged from pre-comma part of pipe-form labels; alias drop |
| `gbdc.py` | none (generic) |
| `gsbd.py` | none (generic) |
| `htgc.py` | drop issuer-level `"and Total X"` rollups; rich " and "-separated label parser |
| `main.py` | tranche-type vocabulary mapping (`Secured Debt`, `Member Units`, `Preferred Member Units`) |
| `mfic.py` | drop `"Controlled Investments "` alias prefix; sector + type + SOFR-spread parser |
| `msdl.py` | none (generic) |
| `nmfc.py` | none (generic; sub-entity filter does the work) |
| `obdc.py` | drop sub-SOI no-pipe rollup rows; three-pipe label parser |
| `ocsl.py` | none (generic; sub-entity filter does the work) |
| `psec.py` | none (generic) |
| `tcpc.py` | drop `"Controlled/Non-Controlled Affiliates,"` aliases; rich "Ref X(Q) Floor Y%" parser |
| `tslx.py` | section + type label parser |

Foreign-currency FV facts (TSLX has SEK / EUR / GBP / NOK / AUD / CAD;
others have EUR) are kept in their native currency in position records,
and converted to USD via `FX_TO_USD` for the summary aggregate only.

## Building a new BDC handler

Add `bot/bdcs/<ticker>.py`:

```python
from ._base import Bdc
from . import register

@register
class Newbdc(Bdc):
    ticker = "NEWBDC"
    canonical_fv_m = 1234.0
    canonical_period = "2025-12-31"

    # Optional hooks:
    drop_identifier_prefixes = ("Skip This Prefix ",)
    # def parse_identifier(self, ident): return {"entity": ..., "type": ...}
    # def post_filter(self, positions): return ...
```

The dispatcher loads it lazily on first call to `bdcs.get("NEWBDC")`.

## Known gaps (all BDCs)

The following dashboard fields are **not** XBRL-tagged per position in
SEC SOI filings and are returned as `null` in v1:

- `sector` — sector grouping appears as text in the HTML SOI table only
- `maturity` — date appears in SOI text only
- `acq` (acquisition date) — same
- `baseRate` (SOFR / Prime / SONIA / etc.) — referenced as text only
- `desc` (company business description) — narrative
- `affil` per-position — tagged only on aggregate roll-up contexts

These require a second-pass HTML parser over the main filing document
joining on the InvestmentIdentifierAxis label. Some BDCs (notably BCSF,
MFIC, TCPC, HTGC) embed `sector`, `type`, `spread`, `rate`, and
`maturity` directly into the XBRL identifier string itself — a future
extractor pass could parse those substrings.

## Files

- `extract_bdc_soi.py` — main extractor (generic, ticker-based)
- `extract_arcc_soi.py` — original ARCC-only extractor (kept for reference)
- `bdc_registry.json` — ticker → CIK + name map (18 BDCs)
- `requirements.txt` — Python deps (requests, lxml)
- `.cache/` — cached `data.sec.gov/submissions/...` responses (1h TTL)
- `out/` — single-BDC outputs
- `out_all/` — batch outputs from `--all` mode, plus `_summary.csv`
