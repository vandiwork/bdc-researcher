"""
ARCC Schedule of Investments extractor.

Pulls per-position SOI data from an ARCC 10-K or 10-Q filing on SEC EDGAR by
parsing the XBRL instance document. Each position is encoded in XBRL as a
typed dimension `us-gaap:InvestmentIdentifierAxis` whose value is the
issuer-tranche label (e.g. "ACP Avenu Midco LLC, First lien senior secured loan").
Numeric facts (fair value, cost, par, rate, spread, PIK rate, shares) hang
off those contexts.

Fields NOT tagged per-position in XBRL — sector, maturity, acquisition date,
base rate name (SOFR/Prime), description, currency — are left null and noted
as enrichment hooks for a future HTML pass.

Usage:
    python extract_arcc_soi.py 0001287750-26-000006
    python extract_arcc_soi.py https://www.sec.gov/Archives/edgar/data/1287750/000128775026000006/
    python extract_arcc_soi.py 0001287750-26-000006 --out ./out --cik 1287750
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import requests
from lxml import etree

ARCC_CIK = "1287750"
DEFAULT_UA = "BDC Researcher contact@example.com"

NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
    "xlink": "http://www.w3.org/1999/xlink",
    "link": "http://www.xbrl.org/2003/linkbase",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


# ── Tranche-type derivation from the InvestmentIdentifierAxis label ──
# ARCC's label is typically "<Issuer Name>, <Investment Description> [<n>]"
# where the second part names the investment type. Order matters: check the
# most specific phrases before generic ones.
TYPE_RULES: list[tuple[str, re.Pattern]] = [
    # ── Debt ──
    ("First Lien",          re.compile(r"\bfirst[- ]lien\b", re.I)),
    ("Second Lien",         re.compile(r"\bsecond[- ]lien\b", re.I)),
    ("Senior Subordinated", re.compile(r"\bsenior subordinated\b", re.I)),
    ("Mezzanine",           re.compile(r"\bmezzanine\b", re.I)),
    ("Unitranche",          re.compile(r"\bunitranche\b", re.I)),
    ("Subordinated",        re.compile(r"\bsubordinated\b", re.I)),
    # ── Equity — most specific first ──
    ("Preferred Equity",    re.compile(r"\bpreferred (?:equity|stock|interest|share|unit|certificate)", re.I)),
    ("Preferred Equity",    re.compile(r"\b(?:senior |class [A-Z][-0-9]*\s+|series [A-Z0-9][-0-9]*\s+)preferred\b", re.I)),
    ("Preferred Equity",    re.compile(r"\b(?:class|series)\s+[A-Z][-0-9]*\s+preferred\s+(?:unit|share|stock)", re.I)),
    ("Warrant",             re.compile(r"\bwarrant", re.I)),
    ("Common Equity",       re.compile(r"\bcommon (?:equity|stock|share|interest|unit)", re.I)),
    ("Common Equity",       re.compile(r"\bordinary shares?\b", re.I)),
    # Class/Series A/B/C/D units — common equity tranches
    ("Common Equity",       re.compile(r"\b(?:class|series)\s+[A-Z][-0-9]*\s+(?:unit|share|stock|interest)", re.I)),
    ("LP Interest",         re.compile(r"\b(?:lp|limited partner(?:ship)?)\s+(?:interest|unit)", re.I)),
    ("LP Interest",         re.compile(r"\bpartnership unit", re.I)),
    ("LLC Interest",        re.compile(r"\b(?:llc|limited liability|member(?:ship)?)\s+interest", re.I)),
    ("Company Units",       re.compile(r"\bcompany units?\b", re.I)),
    ("Participation",       re.compile(r"\bparticipation\s+(?:right|interest)", re.I)),
    # Final catch-all for residual equity-like labels
    ("Equity",              re.compile(r"\b(?:units?|shares?|stock|interests?|equity|membership)\b", re.I)),
]


@dataclass
class Position:
    bdc: str = "ARCC"
    identifier: str = ""            # full InvestmentIdentifierAxis text
    entity: str = ""                # pre-comma issuer name
    company: str = ""               # cleaned short name (= entity by default)
    desc: Optional[str] = None
    sector: Optional[str] = None
    type: str = ""
    affil: str = ""
    fv: Optional[float] = None      # fair value, raw units (USD)
    cost: Optional[float] = None
    par: Optional[float] = None     # principal amount (debt)
    shares: Optional[float] = None  # shares (equity)
    mark: Optional[float] = None    # fv / cost * 100
    spread: Optional[float] = None  # basis spread over variable rate (%)
    rate: Optional[float] = None    # all-in interest rate (%)
    pik_rate: Optional[float] = None
    pik: bool = False
    baseRate: Optional[str] = None
    maturity: Optional[str] = None
    acq: Optional[str] = None
    ccy: str = "USD"


@dataclass
class Filing:
    cik: str
    accession: str          # with dashes, e.g. "0001287750-26-000006"
    accession_raw: str      # no dashes
    form: str = ""
    period_end: str = ""
    file_date: str = ""
    primary_doc: str = ""
    base_url: str = ""


# ── EDGAR helpers ──────────────────────────────────────────────────────

def make_session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov",
    })
    return s


def resolve_filing(arg: str, cik: str, sess: requests.Session) -> Filing:
    """Accept an accession number (with or without dashes) or a full filing
    URL and return a Filing struct with absolute base_url."""
    # URL form?
    m = re.search(
        r"/Archives/edgar/data/(\d+)/(\d{18})(?:/|$)", arg)
    if m:
        cik = m.group(1)
        raw = m.group(2)
        accession = f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"
    else:
        accession = arg.strip()
        raw = accession.replace("-", "")
        if len(raw) != 18 or not raw.isdigit():
            raise ValueError(
                f"Unrecognized accession or URL: {arg!r}\n"
                "Expected '0001287750-26-000006' or a full /Archives/... URL."
            )
        accession = f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"

    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{raw}"
    f = Filing(cik=cik, accession=accession, accession_raw=raw, base_url=base)

    # Enrich with form/period from submissions index
    sub_url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    sess.headers["Host"] = "data.sec.gov"
    try:
        r = sess.get(sub_url, timeout=30)
        if r.ok:
            j = r.json()
            recent = j.get("filings", {}).get("recent", {})
            accs = recent.get("accessionNumber", [])
            for i, a in enumerate(accs):
                if a == accession:
                    f.form = recent["form"][i]
                    f.period_end = recent["reportDate"][i]
                    f.file_date = recent["filingDate"][i]
                    f.primary_doc = recent["primaryDocument"][i]
                    break
    finally:
        sess.headers["Host"] = "www.sec.gov"

    return f


def find_xbrl_instance(filing: Filing, sess: requests.Session) -> str:
    """The XBRL instance is normally <ticker>-<period>_htm.xml inside the
    filing directory. Fall back to scanning the filing index if needed."""
    # Convention: arcc-YYYYMMDD_htm.xml
    candidate = None
    if filing.primary_doc and filing.primary_doc.endswith(".htm"):
        base_name = filing.primary_doc[:-4]   # strip .htm
        candidate = f"{base_name}_htm.xml"
        url = f"{filing.base_url}/{candidate}"
        r = sess.head(url, timeout=30)
        if r.status_code == 200:
            return url

    # Scan filing index page
    idx_url = f"{filing.base_url}/"
    r = sess.get(idx_url, timeout=30)
    r.raise_for_status()
    m = re.search(r'href="([^"]+_htm\.xml)"', r.text)
    if m:
        href = m.group(1)
        if href.startswith("/"):
            return f"https://www.sec.gov{href}"
        return f"{filing.base_url}/{href}"

    raise RuntimeError(
        f"Could not locate XBRL instance document for filing {filing.accession}"
    )


def fetch(url: str, sess: requests.Session, *, retries: int = 3,
          backoff: float = 1.5) -> bytes:
    last_err = None
    for attempt in range(retries):
        try:
            r = sess.get(url, timeout=120)
            if r.status_code == 200:
                return r.content
            last_err = RuntimeError(f"HTTP {r.status_code} for {url}")
        except requests.RequestException as e:
            last_err = e
        time.sleep(backoff ** attempt)
    raise last_err  # type: ignore[misc]


# ── XBRL parsing ───────────────────────────────────────────────────────

@dataclass
class Context:
    cid: str
    period_kind: str = ""        # 'instant' | 'duration'
    period_end: str = ""         # ISO date
    period_start: str = ""       # ISO date if duration
    identifier: Optional[str] = None    # typed InvestmentIdentifierAxis value
    dims: dict[str, str] = field(default_factory=dict)


def parse_contexts(xml_bytes: bytes) -> dict[str, Context]:
    """Walk the instance document and build a context map."""
    root = etree.fromstring(xml_bytes)
    contexts: dict[str, Context] = {}
    ns_xbrli = NS["xbrli"]
    ns_xbrldi = NS["xbrldi"]

    for el in root.findall(f"{{{ns_xbrli}}}context"):
        ctx = Context(cid=el.get("id", ""))

        period = el.find(f"{{{ns_xbrli}}}period")
        if period is not None:
            instant = period.find(f"{{{ns_xbrli}}}instant")
            if instant is not None:
                ctx.period_kind = "instant"
                ctx.period_end = (instant.text or "").strip()
            else:
                start = period.find(f"{{{ns_xbrli}}}startDate")
                end = period.find(f"{{{ns_xbrli}}}endDate")
                ctx.period_kind = "duration"
                ctx.period_start = (start.text if start is not None else "") or ""
                ctx.period_end = (end.text if end is not None else "") or ""

        segment = el.find(f"{{{ns_xbrli}}}entity/{{{ns_xbrli}}}segment")
        if segment is not None:
            for mem in segment.findall(f"{{{ns_xbrldi}}}explicitMember"):
                d = mem.get("dimension") or ""
                v = (mem.text or "").strip()
                ctx.dims[d] = v
            for typed in segment.findall(f"{{{ns_xbrldi}}}typedMember"):
                d = typed.get("dimension") or ""
                # typedMember has a child element whose text is the value
                children = list(typed)
                v = (children[0].text if children else "") or ""
                v = v.strip()
                if d.endswith("InvestmentIdentifierAxis"):
                    ctx.identifier = v
                else:
                    ctx.dims[d] = v
        contexts[ctx.cid] = ctx
    return contexts


# Fact local names we care about
NUMERIC_FACTS = {
    "InvestmentOwnedAtFairValue":          "fv",
    "InvestmentOwnedAtCost":               "cost",
    "InvestmentOwnedBalancePrincipalAmount": "par",
    "InvestmentOwnedBalanceShares":        "shares",
    "InvestmentInterestRate":              "rate",
    "InvestmentBasisSpreadVariableRate":   "spread",
    "InvestmentInterestRatePaidInKind":    "pik_rate",
}

# Some XBRL facts express percentages as decimals (0.0475 = 4.75%), others
# already as percents (4.75). Look at the `decimals` attribute on the fact:
# decimals="-2" or absolute values > 1 typically indicate already-percent.
def _to_percent(text: str, decimals_attr: Optional[str]) -> Optional[float]:
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    # If filer reports a decimal-fraction (e.g. 0.0475), scale up.
    # Heuristic: absolute value <= 1 means decimal-fraction.
    if abs(v) <= 1.0 and v != 0:
        v = v * 100.0
    return round(v, 4)


def parse_facts(
    xml_bytes: bytes, contexts: dict[str, Context], period_end: str
) -> list[Position]:
    """Stream the instance, attaching facts to their context. Return one
    Position per identifier-axis context whose period_end matches."""
    # Group facts by contextRef
    per_ctx: dict[str, dict] = defaultdict(dict)
    units: dict[str, str] = {}     # contextRef -> last-seen unit (for ccy)

    # Use iterparse for memory efficiency on 14 MB instances
    parser = etree.iterparse(io.BytesIO(xml_bytes), events=("end",))
    for _, el in parser:
        qn = etree.QName(el)
        if qn.namespace in (NS["xbrli"], NS["xbrldi"], NS["link"], NS["xlink"], NS["xsi"]):
            continue
        cref = el.get("contextRef")
        if not cref:
            continue
        fname = qn.localname
        if fname not in NUMERIC_FACTS:
            continue
        col = NUMERIC_FACTS[fname]
        text = (el.text or "").strip()
        if not text:
            continue
        if col in ("fv", "cost", "par", "shares"):
            try:
                val = float(text)
            except ValueError:
                continue
            per_ctx[cref][col] = val
            uref = el.get("unitRef") or ""
            if uref:
                units[cref] = uref
        else:
            pct = _to_percent(text, el.get("decimals"))
            if pct is not None:
                per_ctx[cref][col] = pct
        el.clear()

    # ARCC's XBRL exposes investments at two levels: an issuer-level roll-up
    # (identifier = "Issuer Name") and one or more tranche-level leaves
    # (identifier = "Issuer Name, <Tranche description>"). The roll-up FV is
    # the sum of its leaves' FVs, so leaving roll-ups in would double-count.
    # Detect a roll-up as any identifier that is a comma-prefix of some other
    # identifier present in the same period.
    period_ids = {
        contexts[c].identifier
        for c, _ in per_ctx.items()
        if c in contexts and contexts[c].identifier
        and (not period_end or contexts[c].period_end == period_end)
    }
    rollup_ids = set()
    for i in period_ids:
        prefix = i + ","
        # match "X," or "X ," (some ARCC labels have a stray space before the comma)
        for j in period_ids:
            if j is i or j is None:
                continue
            if j.startswith(prefix) or j.startswith(i + " ,"):
                rollup_ids.add(i)
                break

    # A small set of identifier labels are concentration-disclosure
    # placeholders ("Largest Portfolio Company Investment",
    # "Top Five Largest Portfolio Company Investments") that ARCC tags with
    # `InvestmentOwnedPercentOfNetAssets` only — no FV/Cost. Drop them.
    META_IDS = {
        "Largest Portfolio Company Investment",
        "Top Five Largest Portfolio Company Investments",
    }

    # Build positions for contexts that are per-position (have identifier)
    # and whose period_end matches the filing period.
    positions: list[Position] = []
    skipped_rollups = 0
    for cref, data in per_ctx.items():
        ctx = contexts.get(cref)
        if not ctx or not ctx.identifier:
            continue
        if period_end and ctx.period_end != period_end:
            continue
        if ctx.identifier in rollup_ids:
            skipped_rollups += 1
            continue
        if ctx.identifier in META_IDS:
            continue
        # Require at least one of fv/cost — otherwise this context only
        # carried a non-position fact (rate, percent, etc.) and isn't a row.
        if data.get("fv") is None and data.get("cost") is None:
            continue

        ident = ctx.identifier
        entity, type_ = split_identifier(ident)
        unit = units.get(cref, "").lower()
        ccy = "USD"
        if unit and "usd" not in unit:
            # heuristic: convert iso4217-currency to its 3-letter code
            m = re.search(r"([A-Z]{3})$", unit.upper())
            ccy = m.group(1) if m else unit.upper()

        fv = data.get("fv")
        cost = data.get("cost")
        mark = None
        if fv is not None and cost not in (None, 0):
            mark = round(fv / cost * 100, 2)

        pik_rate = data.get("pik_rate")

        affil = ""
        # Map issuer-affiliation by looking up an issuer-level context
        # (same identifier, same period, has InvestmentIssuerAffiliationAxis).
        # Most positions inherit Unaffiliated when not tagged otherwise.
        affil = derive_affiliation(ctx, contexts)

        positions.append(Position(
            identifier=ident,
            entity=entity,
            company=entity,
            type=type_,
            affil=affil,
            fv=fv,
            cost=cost,
            par=data.get("par"),
            shares=data.get("shares"),
            mark=mark,
            spread=data.get("spread"),
            rate=data.get("rate"),
            pik_rate=pik_rate,
            pik=pik_rate is not None and pik_rate > 0,
            ccy=ccy,
        ))
    return positions


def split_identifier(ident: str) -> tuple[str, str]:
    """Split 'Foo, Inc., First lien senior secured loan 2' →
    ('Foo, Inc.', 'First Lien'). The issuer name may contain commas, so we
    try each split position from left to right and accept the first whose
    tail matches a known type phrase. Falls back to scanning the whole
    label for a type phrase (covers cases like 'Doxim Inc. First lien
    senior secured loan' where ARCC's text has no comma)."""
    # Prefer the RIGHTMOST comma split that still yields a recognized type
    # phrase in the tail — preserves corporate suffixes like "Inc.", "LLC",
    # "L.P." in the issuer name. e.g. for
    # "Actfy Buyer, Inc., First lien senior secured loan" we want
    # entity="Actfy Buyer, Inc." not "Actfy Buyer".
    parts = ident.split(",")
    for i in range(len(parts) - 1, 0, -1):
        tail = ",".join(parts[i:]).strip()
        for tname, pat in TYPE_RULES:
            m = pat.search(tail)
            if m:
                entity = ",".join(parts[:i]).strip()
                return entity, tname

    # Fallback: scan the whole identifier for a type phrase and split there.
    for tname, pat in TYPE_RULES:
        m = pat.search(ident)
        if m:
            entity = ident[:m.start()].rstrip(" ,.").strip()
            if entity:
                return entity, tname

    return ident.strip(), ""


AFFIL_MAP = {
    "us-gaap:InvestmentUnaffiliatedIssuerMember": "Unaffiliated",
    "us-gaap:InvestmentAffiliatedIssuerNoncontrolledMember": "Affiliated Non-Controlled",
    "us-gaap:InvestmentAffiliatedIssuerControlledMember": "Affiliated Controlled",
}


def derive_affiliation(_ctx: Context, _contexts: dict[str, Context]) -> str:
    # ARCC tags affiliation only on aggregate roll-up contexts, not per-position.
    # Leave blank for now (v2: derive by joining identifier-stem on issuer-level
    # InvestmentIssuerAffiliationAxis contexts).
    return ""


# ── Output ────────────────────────────────────────────────────────────

def to_dashboard_record(p: Position) -> dict:
    """Project a Position into the JSON shape used by the existing
    arcc_dashboard.html DATA block. Numeric amounts are reported in
    thousands ($K) to match the dashboard convention."""
    def k(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        return round(v / 1000.0, 1)
    return {
        "bdc": p.bdc,
        "entity": p.entity,
        "company": p.company,
        "desc": p.desc,
        "sector": p.sector,
        "type": p.type,
        "affil": p.affil,
        "fv": k(p.fv),
        "cost": k(p.cost),
        "par": k(p.par),
        "mark": p.mark,
        "spread": p.spread,
        "rate": p.rate,
        "baseRate": p.baseRate,
        "maturity": p.maturity,
        "acq": p.acq,
        "ccy": p.ccy,
        "pik": p.pik,
    }


def write_outputs(positions: list[Position], filing: Filing, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = filing.accession.replace("-", "")
    json_path = out_dir / f"ARCC_{tag}.json"
    csv_path = out_dir / f"ARCC_{tag}.csv"

    json_records = [to_dashboard_record(p) for p in positions]
    json_path.write_text(json.dumps(json_records, indent=2), encoding="utf-8")

    csv_cols = [
        "bdc", "cik", "accession", "form", "period_end", "file_date",
        "identifier", "entity", "company", "type", "sector", "desc", "affil",
        "fv", "cost", "par", "shares", "mark",
        "spread", "rate", "base_rate", "pik_rate", "pik",
        "maturity", "acq", "ccy",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=csv_cols)
        w.writeheader()
        for p in positions:
            w.writerow({
                "bdc": p.bdc,
                "cik": filing.cik,
                "accession": filing.accession,
                "form": filing.form,
                "period_end": filing.period_end,
                "file_date": filing.file_date,
                "identifier": p.identifier,
                "entity": p.entity,
                "company": p.company,
                "type": p.type,
                "sector": p.sector or "",
                "desc": p.desc or "",
                "affil": p.affil,
                "fv": p.fv if p.fv is not None else "",
                "cost": p.cost if p.cost is not None else "",
                "par": p.par if p.par is not None else "",
                "shares": p.shares if p.shares is not None else "",
                "mark": p.mark if p.mark is not None else "",
                "spread": p.spread if p.spread is not None else "",
                "rate": p.rate if p.rate is not None else "",
                "base_rate": p.baseRate or "",
                "pik_rate": p.pik_rate if p.pik_rate is not None else "",
                "pik": p.pik,
                "maturity": p.maturity or "",
                "acq": p.acq or "",
                "ccy": p.ccy,
            })
    print(f"  wrote {json_path}  ({len(json_records)} positions)")
    print(f"  wrote {csv_path}")


# ── Main ───────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract Schedule of Investments from an ARCC 10-K/10-Q filing.")
    ap.add_argument("filing",
                    help="EDGAR accession number (e.g. 0001287750-26-000006) "
                         "or full filing-directory URL.")
    ap.add_argument("--cik", default=ARCC_CIK,
                    help=f"Filer CIK (default {ARCC_CIK}).")
    ap.add_argument("--out", default="out",
                    help="Output directory (default ./out)")
    ap.add_argument("--user-agent", default=DEFAULT_UA,
                    help="User-Agent header sent to SEC (SEC requires one).")
    args = ap.parse_args()

    # Force UTF-8 stdout on Windows so progress glyphs don't crash cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    sess = make_session(args.user_agent)

    print(f"[1/5] Resolving filing {args.filing}")
    filing = resolve_filing(args.filing, args.cik, sess)
    print(f"  accession   {filing.accession}")
    print(f"  form        {filing.form or '(unknown)'}")
    print(f"  period_end  {filing.period_end or '(unknown)'}")
    print(f"  base_url    {filing.base_url}")

    if not filing.period_end:
        print("WARNING: could not enrich filing metadata from submissions API; "
              "all positions will be included regardless of period.",
              file=sys.stderr)

    print(f"[2/5] Locating XBRL instance document")
    xml_url = find_xbrl_instance(filing, sess)
    print(f"  {xml_url}")

    print(f"[3/5] Downloading instance (this can be 10-20 MB)")
    xml_bytes = fetch(xml_url, sess)
    print(f"  {len(xml_bytes):,} bytes")

    print(f"[4/5] Parsing contexts")
    contexts = parse_contexts(xml_bytes)
    identifier_ctxs = sum(1 for c in contexts.values() if c.identifier)
    print(f"  {len(contexts):,} total contexts, {identifier_ctxs:,} per-position")

    print(f"[5/5] Parsing facts and building positions")
    positions = parse_facts(xml_bytes, contexts, filing.period_end)
    print(f"  {len(positions):,} leaf positions extracted "
          "(issuer-level roll-ups filtered out)")

    print(f"      Writing outputs")

    if positions:
        total_fv = sum((p.fv or 0) for p in positions)
        total_cost = sum((p.cost or 0) for p in positions)
        print(f"  total FV   ${total_fv/1e6:,.1f}M")
        print(f"  total cost ${total_cost/1e6:,.1f}M")
        by_type: dict[str, int] = defaultdict(int)
        for p in positions:
            by_type[p.type or "(untyped)"] += 1
        print(f"  by type:")
        for t, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
            print(f"    {n:5d}  {t}")

    write_outputs(positions, filing, Path(args.out))

    return 0 if positions else 2


if __name__ == "__main__":
    raise SystemExit(main())
