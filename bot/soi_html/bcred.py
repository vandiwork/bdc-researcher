"""BCRED SOI HTML parser. Blackstone Private Credit Fund — same SOI layout
family as BXSL (sector via section-break rows, values in $thousands)."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class BcredSoi(SoiHtmlParser):
    ticker = "BCRED"
    header_anchor = r"Investments|Reference Rate"
    column_aliases = {"Investments": "company"}
    value_scale_m = 0.001   # BCRED reports SOI values in $K
