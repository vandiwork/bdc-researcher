"""GBDC — Golub Capital BDC, Inc. (CIK 0001476765).

GBDC tags issuer-level "bare" rows ("Chestnut Optical Midco, Inc.")
alongside their tranche leaves. Two leaf-label conventions coexist:

  - comma form  "Chestnut Optical Midco, Inc., One stop 1"
  - PIPE form   "Chestnut Optical Midco, Inc. | One stop 1"

The generic rollup detector only recognises the comma form, so the
pipe-form bares slip through and DOUBLE-COUNT (bare FV + leaf FVs),
leaving GBDC ~1.6% over. `post_filter` below reconciles the pipe-form
bares:
  - bare ≈ Σleaves  → exact rollup, drop the bare
  - bare  > Σleaves  → keep only the excess (untagged holdco equity)
  - bare  < Σleaves  → leaves authoritative, drop the bare
Bares with no leaves (e.g. Fleet Farm Group) are genuine standalone
positions and kept untouched.
"""
from __future__ import annotations
from ._base import Bdc
from . import register

_EXCESS_TAG = " — Other (partial rollup excess)"


@register
class Gbdc(Bdc):
    ticker = "GBDC"
    canonical_fv_m = 8317.2
    canonical_period = "2026-03-31"
    keep_partial_rollup_excess = True

    def post_filter(self, positions: list) -> list:
        # Bare rows = no " | " separator and not the generic extractor's
        # synthetic excess rows (those already carry _EXCESS_TAG).
        bares = [p for p in positions
                 if " | " not in (p.identifier or "")
                 and _EXCESS_TAG not in (p.identifier or "")]
        drop = set()
        adjust = {}
        for bare in bares:
            ent = (bare.identifier or "").strip()
            if not ent:
                continue
            leaves = [p for p in positions
                      if p is not bare
                      and ((p.identifier or "").startswith(ent + " |")
                           or (p.identifier or "").startswith(ent + ","))]
            if not leaves:
                continue  # standalone position — keep as-is
            leaf_fv = sum((p.fv or 0) for p in leaves)
            bare_fv = bare.fv or 0
            tol = max(50_000.0, abs(leaf_fv) * 0.005)
            if abs(bare_fv - leaf_fv) <= tol:
                drop.add(id(bare))                  # exact rollup
            elif bare_fv > leaf_fv:
                adjust[id(bare)] = bare_fv - leaf_fv  # keep holdco excess
            else:
                drop.add(id(bare))                  # leaves authoritative
        out = []
        for p in positions:
            if id(p) in drop:
                continue
            if id(p) in adjust:
                p.fv = adjust[id(p)]
                p.cost = None
                p.mark = None
                p.identifier = (p.identifier or "") + _EXCESS_TAG
            out.append(p)
        return out
