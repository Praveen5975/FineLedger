"""Wastage Agent: proposes wastage from the karigar's OWN history, and flags outliers.

Robust statistics (median + MAD) so one bad batch does not drag the proposal.
With too little history it refuses to guess: no invented industry defaults.
"""
from __future__ import annotations

import math
from statistics import median

from ..accounts import account, karigar_accounts
from ..gold import fmt_mg
from .common import Alert

MIN_SAMPLES = 3
SCALE_FLOOR_BP = 5


def history(ledger, karigar: str, design: str, exclude_order: str | None = None) -> list[dict]:
    out = []
    for a in karigar_accounts(ledger, karigar):
        if a.closed and a.design == design and a.order_id != exclude_order and a.realized_wastage_bp is not None:
            out.append({"order": a.order_id, "agreed_bp": a.agreed_wastage_bp,
                        "realized_bp": a.realized_wastage_bp, "cites": a.cites})
    return out


def _stats(samples: list[int]) -> tuple[float, float]:
    m = median(samples)
    mad = median(abs(x - m) for x in samples)
    return m, max(1.4826 * mad, SCALE_FLOOR_BP)


def propose(ledger, karigar: str, design: str) -> Alert:
    h = history(ledger, karigar, design)
    who = ledger.party(karigar)["name"]
    if len(h) < MIN_SAMPLES:
        return Alert("wastage", "info", design,
                     f"Only {len(h)} past {design} order(s) for {who}; at least {MIN_SAMPLES} needed. "
                     "No proposal - agree wastage manually and record it.",
                     {"suggested_bp": None, "samples": h}, [c for x in h for c in x["cites"]], [karigar])
    xs = [x["realized_bp"] for x in h]
    m, scale = _stats(xs)
    suggested = int(math.ceil(m / 5.0) * 5)
    band = (max(0, int(m - 2 * scale)), int(math.ceil(m + 2 * scale)))
    return Alert("wastage", "info", design,
                 f"{who}'s realised wastage on {design} over {len(h)} orders: median {m:.0f} bp "
                 f"(typical band {band[0]}-{band[1]} bp). Suggested agreement: {suggested} bp "
                 f"({suggested / 100:.2f}%). Both parties decide; this is a starting point.",
                 {"suggested_bp": suggested, "median_bp": m, "band_bp": band, "samples": h,
                  "flag_above_bp": int(math.ceil(m + 3 * scale))},
                 [c for x in h for c in x["cites"]], [karigar])


def flag(ledger, order_id: str) -> Alert | None:
    a = account(ledger, order_id)
    if not a.closed or a.realized_wastage_bp is None:
        return None
    h = history(ledger, a.karigar, a.design, exclude_order=order_id)
    if len(h) < MIN_SAMPLES:
        return None
    m, scale = _stats([x["realized_bp"] for x in h])
    z = (a.realized_wastage_bp - m) / scale
    if z <= 3:
        return None
    return Alert("wastage", "amber", order_id,
                 f"Order {order_id}: realised wastage {a.realized_wastage_bp} bp vs {m:.0f} bp typical "
                 f"for this karigar on {a.design} ({fmt_mg(a.excess_mg)} beyond the agreed allowance). "
                 "This is a prompt to check, not a finding.",
                 {"realized_bp": a.realized_wastage_bp, "median_bp": m, "z": round(z, 1), "excess_mg": a.excess_mg,
                  "check": ["scale photo on the final RETURN", "was all scrap/filings returned?",
                            "any rework or stone-setting loss not recorded?"]},
                 a.cites, [a.jeweller, a.karigar])
