"""MFIC SOI HTML parser. Industry/Company combined column."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class MficSoi(SoiHtmlParser):
    ticker = "MFIC"
    header_anchor = r"Industry/Company"
    value_scale_m = 0.001   # MFIC reports SOI values in $K
