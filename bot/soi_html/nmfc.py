"""NMFC SOI HTML parser. Has Industry baked into Portfolio Company column."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class NmfcSoi(SoiHtmlParser):
    ticker = "NMFC"
    header_anchor = r"Portfolio Company"
    value_scale_m = 0.001   # NMFC reports SOI values in $K
