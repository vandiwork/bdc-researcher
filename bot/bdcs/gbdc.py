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
import re as _re
from ._base import Bdc
from . import register

_EXCESS_TAG = " — Other (partial rollup excess)"


@register
class Gbdc(Bdc):
    ticker = "GBDC"
    canonical_fv_m = 8317.2
    canonical_period = "2026-03-31"
    keep_partial_rollup_excess = True

    def parse_identifier(self, ident: str) -> dict:
        # GBDC identifier: "<Entity> | <Tranche> | <Affiliation>"
        #   e.g. "PPW Aero Buyer, Inc. | One stop 1 | Non-Affiliated Issuer"
        # Entity is just the first segment; the generic splitter keeps the
        # whole pipe string, so parse it explicitly here.
        base = ident.split(_EXCESS_TAG)[0]
        parts = [p.strip() for p in base.split(" | ")]
        entity = parts[0]
        tranche = parts[1] if len(parts) >= 2 else ""
        # Some GBDC leaves use a COMMA-form tranche on the bare entity, e.g.
        # "MMan Acquisition Co., One stop 1" (no pipe). Peel that off too.
        m = _re.search(r",\s*(One stop|Senior secured|Second lien|Subordinated|"
                       r"Mezzanine|LLC interest|Preferred|Warrant|Common|Equity|"
                       r"Units|Partnership|Membership)\b.*$", entity, _re.I)
        if m and not tranche:
            tranche = entity[m.start():].lstrip(", ").strip()
            entity = entity[:m.start()].strip()
        out: dict = {"entity": entity}
        if tranche:
            tr = _re.sub(r"\s*\d+\s*$", "", tranche.lower()).strip()
            if "one stop" in tr or "senior secured" in tr or "first lien" in tr:
                out["type"] = "First Lien"   # Golub "one stop" = unitranche/1L
            elif "second lien" in tr:
                out["type"] = "Second Lien"
            elif "subordinated" in tr or "mezz" in tr:
                out["type"] = "Subordinated"
            elif "preferred" in tr:
                out["type"] = "Preferred Equity"
            elif "warrant" in tr:
                out["type"] = "Warrant"
            elif any(k in tr for k in ("llc interest", "equity", "common", "units",
                                       "partnership", "membership", "stock")):
                out["type"] = "Common Equity"
        return out

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
