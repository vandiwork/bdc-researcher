"""BBDC SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class BbdcSoi(SoiHtmlParser):
    ticker = "BBDC"
    # Anchor on "Acq. Date" — only appears in the main SOI header, not
    # the unfunded-commitments table that uses just 3 columns.
    header_anchor = r"Acq\. Date"
    value_scale_m = 0.001   # BBDC reports SOI values in $K
