"""Occasion Agent: works back from the customer's fixed date and warns early.

The load penalty and buffer are tunable heuristics to be calibrated in the field
(interview question 6: how many karigars/open orders does a typical shop handle?).
"""
from __future__ import annotations

from datetime import date
from statistics import median

from ..accounts import account, day_of, karigar_accounts
from .common import Alert


def turnaround_days(ledger, karigar: str, design: str | None = None) -> list[int]:
    out = []
    for a in karigar_accounts(ledger, karigar):
        if a.closed and a.first_issue_on and (design is None or a.design == design):
            out.append((a.delivered_on - a.first_issue_on).days)
    return out


def _first_issue(ledger, order_id: str):
    """Planning uses issues that are recorded but not yet confirmed; only disputed ones are skipped."""
    days = [day_of(r.ts) for r in ledger.entries(order_id=order_id, kind="ISSUE") if ledger.status(r.seq) != "disputed"]
    return min(days) if days else None


def _open_count(ledger, karigar: str, exclude: str) -> int:
    return sum(1 for a in karigar_accounts(ledger, karigar) if not a.closed and a.order_id != exclude)


def assess(ledger, order_id: str, today: date, load_penalty: float = 0.15, buffer_days: float = 2.0) -> Alert | None:
    a = account(ledger, order_id)
    if a.closed:
        return None
    hist = turnaround_days(ledger, a.karigar, a.design) or turnaround_days(ledger, a.karigar)
    days_left = (a.due - today).days
    if not hist:
        return Alert("occasion", "info", order_id,
                     f"No delivery history for {ledger.party(a.karigar)['name']} yet - cannot estimate. "
                     f"{days_left} days to the due date.", {"days_left": days_left}, a.cites, [a.jeweller])
    med = median(hist)
    first = _first_issue(ledger, order_id)
    elapsed = (today - first).days if first else 0
    remaining = med if not first else max(med - elapsed, 1)
    others = _open_count(ledger, a.karigar, order_id)
    expected = remaining * (1 + load_penalty * others)
    slack = days_left - expected
    level = "red" if slack < 0 else "amber" if slack < buffer_days else "green"
    return Alert("occasion", level, order_id,
                 f"Order {order_id} ({a.design}) due {a.due}: {days_left} days left, about {expected:.1f} days of work "
                 f"expected (median {med:.0f} days, {others} other open order(s)). Risk: {level.upper()}.",
                 {"days_left": days_left, "expected_days": round(expected, 1), "slack": round(slack, 1),
                  "median_turnaround": med, "other_open_orders": others},
                 sorted(set(a.cites) | {r.seq for r in ledger.entries(order_id=order_id, kind="ISSUE")}),
                 [a.jeweller, a.karigar])


def suggest_reassign(ledger, order_id: str, today: date, load_penalty: float = 0.15) -> list[dict]:
    """Rank other karigars who could still make the date. A recommendation only: moving
    gold means new ISSUE/RETURN entries that every party must confirm."""
    a = account(ledger, order_id)
    days_left = (a.due - today).days
    out = []
    for k in {o["karigar"] for o in ledger.orders()} - {a.karigar}:
        h = turnaround_days(ledger, k, a.design)
        if not h:
            continue
        exp = median(h) * (1 + load_penalty * _open_count(ledger, k, order_id))
        if exp <= days_left:
            out.append({"karigar": k, "expected_days": round(exp, 1)})
    return sorted(out, key=lambda x: x["expected_days"])
