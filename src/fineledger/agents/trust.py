"""Trust Passport: the karigar's verified record, owned by the karigar.

Design choices that matter:
 * Shows components, not one opaque score, so every number can be explained.
 * Lateness caused by the jeweller or the customer (a CONFIRMED delay note) is not held against the karigar.
 * Sharing needs the karigar's consent; he can withdraw it.
"""
from __future__ import annotations

from statistics import median

from ..accounts import karigar_accounts

MIN_ORDERS = 5


def passport(ledger, karigar: str) -> dict:
    accts = [a for a in karigar_accounts(ledger, karigar) if a.closed]
    excused = set()
    for r in ledger.effective(karigar=karigar):
        if r.data["kind"] == "DELAY_NOTE" and r.data["cause"] in ("jeweller", "customer"):
            excused.add(r.data["order_id"])
    late = [a for a in accts if a.delivered_on > a.due]
    late_counted = [a for a in late if a.order_id not in excused]
    n = len(accts)
    within = [a for a in accts if a.excess_mg == 0]
    clean = [a for a in accts if not a.disputed]
    walls = [x for x in (a.realized_wastage_bp for a in accts) if x is not None]
    spread = round(median(abs(x - median(walls)) for x in walls)) if walls else None
    out = {"karigar": karigar, "name": ledger.party(karigar)["name"], "orders_delivered": n,
           "on_time_rate": round(1 - len(late_counted) / n, 3) if n else None,
           "late_orders": len(late), "late_excused_jeweller_or_customer": len(late) - len(late_counted),
           "within_agreed_wastage_rate": round(len(within) / n, 3) if n else None,
           "wastage_consistency_spread_bp": spread,
           "orders_without_open_dispute_rate": round(len(clean) / n, 3) if n else None}
    if n < MIN_ORDERS:
        out["band"] = "insufficient data"
    elif out["on_time_rate"] >= 0.8 and out["within_agreed_wastage_rate"] >= 0.8:
        out["band"] = "strong record"
    else:
        out["band"] = "mixed record"
    out["how_to_read"] = ("Components, not a hidden score. Lateness caused by the jeweller or customer is excluded "
                          "when both parties confirmed the delay note. Thresholds are illustrative.")
    return out


def export_passport(ledger, karigar: str, grantee: str) -> dict:
    if not ledger.has_consent(karigar, grantee):
        raise PermissionError(f"{karigar} has not shared the passport with {grantee}")
    return passport(ledger, karigar)
