"""The agent loop: observe the ledger -> decide -> notify. Humans approve anything that matters.

run_agents() is stateless and idempotent over a given ledger snapshot; a scheduler (cron,
a queue worker) would call it periodically and hand the Messages to a WhatsApp gateway.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..accounts import account
from ..messages import Message, confirm_request, render
from . import occasion, payments, wastage


def run_agents(ledger, now: datetime, confirm_after_hours: int = 24, flag_window_days: int = 14) -> list[Message]:
    today = now.date()
    msgs: list[Message] = []

    # 1. entries still waiting for the other party
    for r in ledger.entries(status="pending"):
        age = now - datetime.fromisoformat(r.ts)
        if age >= timedelta(hours=confirm_after_hours):
            d = r.data
            other = d["karigar"] if d["by"] == d["jeweller"] else d["jeweller"]
            msgs.append(confirm_request(ledger, r, other))

    for o in ledger.orders():
        a = account(ledger, o["order_id"])
        # 2. delivery risk against the customer's date
        al = occasion.assess(ledger, o["order_id"], today)
        if al and al.level in ("amber", "red"):
            for p in al.to:
                msgs.append(Message(p, "en", "risk_alert", al.summary, al.cites))
        # 3. wastage outliers on recently delivered orders
        if a.closed and (today - a.delivered_on).days <= flag_window_days:
            fl = wastage.flag(ledger, o["order_id"])
            if fl:
                for p in fl.to:
                    msgs.append(Message(p, "en", "wastage_flag", fl.summary, fl.cites))
        # 4. entries that do not add up
        for note in a.anomalies:
            for p in (a.jeweller, a.karigar):
                msgs.append(Message(p, "en", "anomaly", f"Order {a.order_id}: {note}", a.cites))

    # 5. payment waiting time, visible to both sides
    for al in payments.assess(ledger, today):
        for p in al.to:
            lang = ledger.party(p)["lang"]
            text = render("payment_due", lang, order=al.subject, days=al.details["days_waited"],
                          amount=f"{al.details['outstanding_paise'] / 100:,.0f}")
            msgs.append(Message(p, lang, "payment_due", text, al.cites))
    return msgs
