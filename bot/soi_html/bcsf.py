"""BCSF SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class BcsfSoi(SoiHtmlParser):
    ticker = "BCSF"
    header_anchor = r"Portfolio Company"
    value_scale_m = 0.001   # BCSF reports SOI values in $K
