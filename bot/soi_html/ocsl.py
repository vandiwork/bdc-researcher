"""OCSL SOI HTML parser. Has dedicated Industry column."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class OcslSoi(SoiHtmlParser):
    ticker = "OCSL"
    header_anchor = r"Portfolio Company"
    value_scale_m = 0.001   # OCSL reports SOI values in $K
