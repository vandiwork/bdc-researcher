"""TCPC SOI HTML parser. Sector via section-break rows."""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class TcpcSoi(SoiHtmlParser):
    ticker = "TCPC"
    header_anchor = r"Issuer"
    value_scale_m = 1e-6   # TCPC reports SOI values in raw $
