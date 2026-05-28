"""CGBD SOI HTML parser. Has dedicated Industry column."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class CgbdSoi(SoiHtmlParser):
    ticker = "CGBD"
    header_anchor = r"Investments|Reference Rate"
    column_aliases = {
        "Investments—non-controlled/non-affiliated": "company",
        "Investments—controlled/affiliated": "company",
    }
    value_scale_m = 0.001   # CGBD reports SOI values in $K
