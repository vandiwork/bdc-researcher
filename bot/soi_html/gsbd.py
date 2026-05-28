"""GSBD SOI HTML parser. Has dedicated Industry column."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class GsbdSoi(SoiHtmlParser):
    ticker = "GSBD"
    header_anchor = r"Industry|Portfolio Company"
    column_aliases = {"Investment": "company"}
    value_scale_m = 0.001   # GSBD reports SOI values in $K
