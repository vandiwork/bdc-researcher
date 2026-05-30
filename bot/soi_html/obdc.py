"""OBDC SOI HTML parser. Sector via section-break rows.

In Q1 2026, OBDC's column layout split "Par / Units" into two adjacent
cells: "Par" + "Shares/Units". The old `r"Par\\s*/\\s*Units"` anchor
only matched a later sub-SOI page (Investment Funds / Drawn-Undrawn
breakouts), so the main SOI table starting ~17 pages earlier was
skipped entirely. Use "Amortized Cost" — it appears once per SOI page
header in both layouts.

OBDC's SOI is split into Non-Controlled, Affiliated, Controlled, and
Investment Funds sub-sections; each ends with a "Total Investments"
subtotal label. The default `soi_end_markers` matches that label and
stops parsing after the first subsection — losing ~110 positions.
Override to only match the grand-total label ("Total Investments at
Fair Value") that ends the entire SOI."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class ObdcSoi(SoiHtmlParser):
    ticker = "OBDC"
    header_anchor = r"Amortized Cost"
    # Split-cell Par + Shares/Units layout — alias "Par" to principal.
    column_aliases = {"Par": "principal"}
    # Override base end-markers — base's "Total Investments" matches
    # OBDC's subsection subtotals; use only the grand-total variants.
    soi_end_markers = (
        "Total Investments at Fair Value",
        "Total Investments at fair value",
    )
    value_scale_m = 0.001   # OBDC reports SOI values in $K
