"""MSDL SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class MsdlSoi(SoiHtmlParser):
    ticker = "MSDL"
    header_anchor = r"Investments|Reference Rate"
    column_aliases = {"Investments": "company"}
    value_scale_m = 0.001   # MSDL reports SOI values in $K
