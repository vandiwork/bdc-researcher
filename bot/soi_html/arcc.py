"""ARCC SOI HTML parser.

Uses the generic base parser. ARCC has 13 SOI columns including
Business Description and uses section-break rows for sector grouping.
"""
from __future__ import annotations
from . import register
from ._base import SoiHtmlParser


@register
class ArccSoi(SoiHtmlParser):
    ticker = "ARCC"
    header_anchor = r"Company \(1\)"
    known_sectors = (
        "Software and Services",
        "Healthcare Services",
        "Health Care Equipment and Services",
        "Pharmaceuticals, Biotechnology and Life Sciences",
        "Commercial and Professional Services",
        "Insurance Services",
        "Insurance",
        "Capital Goods",
        "Consumer Services",
        "Consumer Durables and Apparel",
        "Consumer Distribution and Retail",
        "Automobiles and Components",
        "Household and Personal Products",
        "Food and Beverage",
        "Food, Beverage and Tobacco",
        "Materials",
        "Transportation",
        "Real Estate",
        "Energy",
        "Financial Services",
        "Diversified Financials",
        "Banks",
        "Media and Entertainment",
        "Sports, Media and Entertainment",
        "Utilities",
        "Gas Utilities",
        "Telecommunication Services",
        "Investment Funds and Vehicles",
        "Power Generation",
        "Independent Power and Renewable Electricity Producers",
        "Retailing",
    )
