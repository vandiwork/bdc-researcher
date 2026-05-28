"""OBDC SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class ObdcSoi(SoiHtmlParser):
    ticker = "OBDC"
    # "Par / Units" is unique to OBDC's main SOI header
    header_anchor = r"Par\s*/\s*Units"
    value_scale_m = 0.001   # OBDC reports SOI values in $K
