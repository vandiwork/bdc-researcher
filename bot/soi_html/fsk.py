"""FSK SOI HTML parser.

FSK's "Rate" column shows the FORMULA (e.g. "SF + 6.0 %"), not an
all-in rate. Treat the percentage in that column as `spread`, not
`interest_rate`. FSK doesn't disclose all-in rate at position level.
"""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class FskSoi(SoiHtmlParser):
    ticker = "FSK"
    header_anchor = r"Portfolio Company"
    # Remap FSK's "Rate" header → spread (it's actually spread, not rate)
    column_aliases = {"Rate": "spread"}
