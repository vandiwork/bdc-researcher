"""GBDC SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class GbdcSoi(SoiHtmlParser):
    ticker = "GBDC"
    # Anchor on contiguous header text that appears in the raw HTML
    # (GBDC splits "Spread Above Index" across <div>s, so we use the
    # neighboring "Amortized Cost" which is a single span)
    header_anchor = r"Amortized Cost|Percentage of Net Assets"
    # GBDC's issuer-name column at col[3-6] has no header label —
    # inject it explicitly so positions parse correctly.
    extra_columns = {(3, 6): "company"}
    value_scale_m = 0.001   # GBDC reports SOI values in $K
