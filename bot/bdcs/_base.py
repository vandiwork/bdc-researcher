"""Base class for per-BDC extraction handlers.

Subclasses live in `bdcs/<ticker>.py` and override only the hooks they
need. The generic extractor calls these hooks at the right stages.

Subclasses use plain class attributes (not dataclass fields) so that
declaring `ticker = "BBDC"` actually overrides the base default. Mutable
defaults are set via `__init_subclass__`.
"""
from __future__ import annotations

import re
from typing import Optional


class Bdc:
    """Per-BDC extraction handler. Override only what's filer-specific."""

    # ── Identity ──────────────────────────────────────────────────────
    ticker: str = ""

    # ── Validation target ─────────────────────────────────────────────
    # Filer-canonical portfolio FV in $M, as published by the BDC in their
    # latest 10-K balance sheet / portfolio table. Used as the validation
    # acceptance target (extracted-sum within 1%).
    canonical_fv_m: Optional[float] = None
    canonical_period: Optional[str] = None    # YYYY-MM-DD

    # ── Filter knobs ──────────────────────────────────────────────────
    # Segment dimensions allowed on per-position contexts. Anything else
    # marks a JV / sub-entity SOI row and is dropped.
    allowed_position_dims: frozenset[str] = frozenset({
        "us-gaap:InvestmentIdentifierAxis",
        "us-gaap:InvestmentIssuerAffiliationAxis",
        "us-gaap:InvestmentIssuerNameAxis",
    })

    # Identifier prefixes / substrings / exact labels to drop.
    drop_identifier_prefixes: tuple[str, ...] = ()
    drop_identifier_patterns: tuple[re.Pattern, ...] = ()
    drop_identifier_exact: frozenset[str] = frozenset()

    # Some filers (GBDC) tag the issuer-level "bare" identifier with an
    # FV that exceeds the sum of its leaf tranches (because the filer
    # didn't tag every position at leaf level). When True, the extractor
    # emits a synthetic "<issuer> — Other" position carrying the excess
    # FV (bare_FV - leaf_sum) so the dashboard total matches canonical.
    keep_partial_rollup_excess: bool = False

    # A few filers (FSK, MSDL) tag their Schedule of Investments at a finer
    # line-item granularity than rolls into their OWN reported "Total
    # Investments at Fair Value". Their per-position inline-XBRL facts (each
    # individually correct vs the SOI) sum ~8–11% above the filer's stated
    # total fact — an internal inconsistency in the filing itself, with no
    # duplicate identifier / dimension / value signature to net out. When
    # this flag is set AND the extracted sum exceeds canonical_fv_m by more
    # than 2%, scale every position's fv/cost/par by canonical/extracted so
    # the portfolio foots to the filer's authoritative total. Scaling fv and
    # cost by the same factor preserves each position's mark (fv/cost) and
    # all relative weights (sector mix, concentration, cross-holdings).
    reconcile_to_reported: bool = False

    # ── Hooks ─────────────────────────────────────────────────────────

    def should_drop_context(self, ctx) -> bool:
        """Return True to skip a context entirely."""
        for d in ctx.dims:
            if d not in self.allowed_position_dims:
                return True
        return False

    def should_drop_identifier(self, ident: str) -> bool:
        """Return True to skip an identifier label."""
        if not ident:
            return True
        if ident in self.drop_identifier_exact:
            return True
        for p in self.drop_identifier_prefixes:
            if ident.startswith(p):
                return True
        for r in self.drop_identifier_patterns:
            if r.search(ident):
                return True
        return False

    def parse_identifier(self, ident: str) -> dict:
        """Parse an identifier label into structured fields.

        Returns any of: entity, type, sector, base_rate, spread (%),
        rate (%), maturity (YYYY-MM-DD), ccy, desc. Unparseable fields
        omitted. Generic extractor falls back to default comma-split."""
        return {}

    def post_filter(self, positions: list) -> list:
        """Final post-processing pass. Returns the (possibly trimmed)
        position list. Override to apply BDC-specific dedup."""
        return positions
