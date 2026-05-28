"""PSEC SOI HTML parser. Has dedicated Industry column."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class PsecSoi(SoiHtmlParser):
    ticker = "PSEC"
    # PSEC uses NBSP between "Portfolio" and "Company" — use a different
    # anchor that's contiguous in raw HTML
    header_anchor = r"Amortized Cost|Legal Maturity"
    column_aliases = {
        "Investments": "investment_type",
        "Investment Type": "investment_type",
        # PSEC uses "Portfolio\xa0Company" with NBSP — accept variants
    }
    value_scale_m = 0.001   # PSEC reports SOI values in $K
