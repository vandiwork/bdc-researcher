"""HTGC SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class HtgcSoi(SoiHtmlParser):
    ticker = "HTGC"
    header_anchor = r"Portfolio Company"
    value_scale_m = 0.001   # HTGC reports SOI values in $K
