"""Shared position-row helpers used by both build_dashboards.py and
build_site_data.py.

These three pieces (FX normalization, the price/mark rule, and the
floating-rate fill) were previously duplicated verbatim in both builders,
which meant every fix had to be applied twice — and a missed copy silently
diverged the per-BDC dashboards from the cross-BDC views. Keeping them here
guarantees one source of truth.
"""
from __future__ import annotations

# Native -> USD. Foreign-currency FV/cost/par are stored native; converting
# here keeps totals and per-position values comparable across the book.
FX_TO_USD = {
    "USD": 1.0, "EUR": 1.04, "GBP": 1.25, "CAD": 0.71, "AUD": 0.62, "CHF": 1.10,
    "SEK": 0.094, "NOK": 0.094, "DKK": 0.14, "SGD": 0.74, "NZD": 0.57,
    "JPY": 0.0064, "ZAR": 0.054, "INR": 0.012, "MXN": 0.049, "BRL": 0.16,
}

_DEBT_TYPES = {"First Lien", "Second Lien", "Subordinated", "Unsecured",
               "Senior Subordinated", "Mezzanine"}


def fx_rate(ccy: str) -> float:
    return FX_TO_USD.get((ccy or "USD").strip().upper(), 1.0)


def compute_mark(fv, cost, par, type_canonical=None, stored=None):
    """Position mark = PRICE (fv/par). Caveats handled here:
      - par as TOTAL commitment (incl. undrawn) deflates fv/par on funded
        loans; when fv/par looks distressed but fv/cost is healthy, par is
        overstated -> use fv/cost (e.g. GSBD term loans).
      - negative fair value (unfunded commitment) -> no meaningful mark.
      - implausible debt price (>130 / <0 from par=0 or negative cost) -> None.
    fv/cost/par are expected in a single currency (ratios are FX-invariant).
    """
    ppar = (fv / par * 100) if (par and par > 0 and fv is not None) else None
    pcost = (fv / cost * 100) if (cost and cost > 0 and fv is not None) else None
    # Par reported as the TOTAL commitment (funded + undrawn) deflates fv/par on
    # a funded loan. When par materially exceeds cost AND the cost-basis price is
    # in a normal funded-loan band, cost tracks the funded face, so fv/cost is
    # the true price (e.g. GSBD Smarsh: fv/par 84 but fv/cost 99 = the co-lender
    # consensus). Outside that band — deep discount, big appreciation (Sorenson
    # fv/cost 148), or a barely-funded DDTL (par many× cost) — fv/par stays the
    # safer figure rather than letting fv/cost overstate.
    par_inflated = (par and cost and cost > 0 and par > cost * 1.08
                    and pcost is not None and 90 <= pcost <= 103)
    if par_inflated:
        mark = pcost
    elif ppar is not None and 0 < ppar <= 130:
        mark = ppar
    elif pcost is not None:
        mark = pcost
    else:
        mark = stored
    if mark is not None:
        mark = round(mark, 2)
    if fv is not None and fv < 0:
        return None
    if mark is not None and (mark > 130 or mark < 0) and (type_canonical or "") in _DEBT_TYPES:
        return None
    return mark


def fill_floating_rates(rows: list) -> dict:
    """Show a coherent all-in Rate for floating-rate loans whose filing only
    reported spread + floor (notably MFIC, where the floor leaked into the rate
    column so Rate < Spread). Derive each index's reference rate empirically —
    median of (reported all-in - spread) across loans that DO report an all-in
    (SOFR ~ 3.7%) — then set rate = reference + spread where the reported rate
    is missing or below the spread. Unparsed base defaults to the dominant
    index (SOFR); an un-pricable floor (e.g. Prime) is blanked rather than
    shown below its spread. Mutates rows in place; returns the reference map."""
    import statistics
    from collections import defaultdict
    imp = defaultdict(list)
    for r in rows:
        b = (r.get("baseRate") or "").upper()
        rt, sp = r.get("rate"), r.get("spread")
        # Only learn the reference from loans whose reported all-in is at least
        # 1pt ABOVE the spread — a real index (SOFR ~3.7, EURIBOR ~2.5) is never
        # near zero. Loans that report rate == spread (the filer put the spread
        # in the rate column) imply a 0 reference and would drag the median down.
        if b and rt and sp and (rt - sp) >= 1.0 and rt < 30:
            imp[b].append(rt - sp)
    ref = {b: round(statistics.median(v), 2) for b, v in imp.items()
           if len(v) >= 20 and statistics.median(v) >= 1.0}
    default = ref.get("SOFR")
    for r in rows:
        b = (r.get("baseRate") or "").upper()
        sp, rt = r.get("spread"), r.get("rate")
        if not sp:
            continue
        rr = ref.get(b)
        if rr is None and b in ("", "SOFR"):
            rr = default
        # rate <= spread means the reported figure can't be a real all-in
        # (all-in = reference + spread > spread); the filer reported just the
        # spread or a floor. Replace with reference + spread.
        if rr and (rt is None or rt <= sp):
            r["rate"] = round(rr + sp, 2)
            r["rate_est"] = True
        elif rt is not None and rt <= sp:
            r["rate"] = None
            r["rate_est"] = True
    return ref
