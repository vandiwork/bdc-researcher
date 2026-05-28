"""NMFC — New Mountain Finance Corp (CIK 0001496099).

NMFC consolidates SLF JVs and similar vehicles (filtered out via the
standard `InvestmentCompanyNonconsolidatedSubsidiaryAxis` dimension).

NMFC also tags non-accrual loans twice: once with the canonical
`Issuer | Tranche` identifier, and a second time with `| Non-accrual
status` appended. Both rows share the same FV. Drop the alias.
"""
from __future__ import annotations
import re
from ._base import Bdc
from . import register


@register
class Nmfc(Bdc):
    ticker = "NMFC"
    canonical_fv_m = 2742.0
    canonical_period = "2025-12-31"

    drop_identifier_patterns = (
        re.compile(r"\|\s*Non-accrual status\s*$", re.I),
    )
