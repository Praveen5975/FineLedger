"""Payment Agent: starts a clock on delivery and shows the wait to BOTH sides.

Late payment is made as visible as late delivery. Jewellers get a payer record too.
"""
from __future__ import annotations

from datetime import date

from ..accounts import account
from .common import Alert


def assess(ledger, today: date, grace_days: int = 3, escalate_days: int = 10) -> list[Alert]:
    out = []
    for o in ledger.orders():
        a = account(ledger, o["order_id"])
        if not a.closed or a.outstanding_paise <= 0:
            continue
        waited = (today - a.delivered_on).days
        if waited <= grace_days:
            continue
        level = "red" if waited >= escalate_days else "amber"
        out.append(Alert("payment", level, a.order_id,
                         f"Order {a.order_id}: delivered {waited} days ago, Rs {a.outstanding_paise / 100:,.0f} unpaid.",
                         {"days_waited": waited, "outstanding_paise": a.outstanding_paise},
                         a.cites, [a.jeweller, a.karigar]))
    return out


def jeweller_record(ledger, jeweller: str) -> dict:
    waits, open_n, oldest = [], 0, 0
    for o in ledger.orders(jeweller=jeweller):
        a = account(ledger, o["order_id"])
        if a.closed and a.paid_on:
            waits.append((a.paid_on - a.delivered_on).days)
        elif a.closed and a.outstanding_paise > 0:
            open_n += 1
    avg = round(sum(waits) / len(waits), 1) if waits else None
    return {"orders_paid": len(waits), "avg_days_to_pay": avg, "orders_unpaid": open_n}
