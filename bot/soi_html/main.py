"""MAIN SOI HTML parser.

MAIN has 12 columns including Business Description. Sector grouping
appears as section-break rows in the body."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class MainSoi(SoiHtmlParser):
    ticker = "MAIN"
    header_anchor = r"Portfolio Company"
    value_scale_m = 0.001   # MAIN reports SOI values in $K
