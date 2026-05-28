"""TSLX SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class TslxSoi(SoiHtmlParser):
    ticker = "TSLX"
    header_anchor = r"Company"
    value_scale_m = 0.001   # TSLX reports SOI values in $K
