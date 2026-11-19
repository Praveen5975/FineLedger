"""Turn confirmed ledger entries into per-order accounts and statements.

Convention (an ASSUMPTION to validate in the field, see docs/FIELD_VALIDATION.md):
agreed wastage is the loss the jeweller accepts. Loss beyond it is owed by the karigar.
Loss = issued - returned - scrap returned - refiner recovery, all in fine gold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .gold import fmt_mg


def day_of(ts: str) -> date:
    return datetime.fromisoformat(ts).date()


@dataclass
class OrderAccount:
    order_id: str
    jeweller: str
    karigar: str
    design: str
    due: date
    labour_paise: int = 0
    issued_mg: int = 0
    returned_mg: int = 0
    scrap_mg: int = 0
    recovery_mg: int = 0
    allowed_mg: int = 0
    with_karigar_mg: int = 0  # gold still in the workshop on an open order: NOT a loss
    loss_mg: int = 0
    excess_mg: int = 0
    agreed_wastage_bp: int | None = None
    realized_wastage_bp: int | None = None
    first_issue_on: date | None = None
    delivered_on: date | None = None
    paid_on: date | None = None
    paid_paise: int = 0
    outstanding_paise: int = 0
    closed: bool = False
    pending: list[int] = field(default_factory=list)
    disputed: list[int] = field(default_factory=list)
    cites: list[int] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.__dict__.items()}


def account(ledger, order_id: str) -> OrderAccount:
    o = ledger.order(order_id)
    a = OrderAccount(order_id, o["jeweller"], o["karigar"], o["design"], date.fromisoformat(o["due"]),
                     labour_paise=o["labour_paise"])
    payments = []
    for r in ledger.effective(order_id=order_id):
        d, k = r.data, r.data["kind"]
        a.cites.append(r.seq)
        if k == "ISSUE":
            a.issued_mg += d["fine_mg"]
            a.allowed_mg += (d["fine_mg"] * d["wastage_bp"] + 5000) // 10000
            day = day_of(r.ts)
            a.first_issue_on = day if a.first_issue_on is None else min(a.first_issue_on, day)
        elif k == "RETURN":
            a.returned_mg += d["fine_mg"]
            if d.get("final"):
                day = day_of(r.ts)
                a.delivered_on = day if a.delivered_on is None else min(a.delivered_on, day)
        elif k == "SCRAP":
            a.scrap_mg += d["fine_mg"]
        elif k == "RECOVERY":
            a.recovery_mg += d["fine_mg"]
        elif k == "PAYMENT":
            payments.append((day_of(r.ts), d["amount_paise"]))
    a.closed = a.delivered_on is not None
    balance = a.issued_mg - a.returned_mg - a.scrap_mg - a.recovery_mg
    if a.issued_mg:
        a.agreed_wastage_bp = round(a.allowed_mg * 10000 / a.issued_mg)
    if a.closed:
        a.loss_mg = balance
        a.excess_mg = max(0, a.loss_mg - a.allowed_mg)
        if a.issued_mg:
            a.realized_wastage_bp = round(a.loss_mg * 10000 / a.issued_mg)
    else:
        a.with_karigar_mg = max(0, balance)
    if balance < 0:
        a.anomalies.append(f"{fmt_mg(-balance)} more fine gold accounted for than was issued - check the entries")
    a.paid_paise = sum(p for _, p in payments)
    if a.closed:
        a.outstanding_paise = max(0, a.labour_paise - a.paid_paise)
        running = 0
        for day, amt in sorted(payments):
            running += amt
            if running >= a.labour_paise:
                a.paid_on = day
                break
    for r in ledger.entries(order_id=order_id):
        st = ledger.status(r.seq)
        if st == "pending":
            a.pending.append(r.seq)
        elif st == "disputed":
            a.disputed.append(r.seq)
    return a


def karigar_accounts(ledger, karigar: str, jeweller: str | None = None) -> list[OrderAccount]:
    return [account(ledger, o["order_id"]) for o in ledger.orders(karigar=karigar, jeweller=jeweller)]


def statement(ledger, karigar: str, jeweller: str | None = None) -> str:
    """Plain-text account a karigar (or his jeweller) can read, forward or print."""
    lines = [f"ACCOUNT STATEMENT - {ledger.party(karigar)['name']} ({karigar})"]
    for a in karigar_accounts(ledger, karigar, jeweller):
        lines.append(f"\nOrder {a.order_id} - {a.design} - for {ledger.party(a.jeweller)['name']} - due {a.due}")
        lines.append(f"  fine gold issued {fmt_mg(a.issued_mg)} | returned {fmt_mg(a.returned_mg)} | "
                     f"scrap {fmt_mg(a.scrap_mg)} | refiner recovery {fmt_mg(a.recovery_mg)}")
        if a.closed:
            lines.append(f"  agreed wastage {fmt_mg(a.allowed_mg)} | loss {fmt_mg(a.loss_mg)} | owed beyond wastage {fmt_mg(a.excess_mg)}")
            lines.append(f"  labour Rs {a.labour_paise / 100:,.0f} | paid Rs {a.paid_paise / 100:,.0f} | outstanding Rs {a.outstanding_paise / 100:,.0f}")
        else:
            lines.append(f"  IN PROGRESS: {fmt_mg(a.with_karigar_mg)} fine gold with the karigar (not a loss)")
        if a.pending:
            lines.append(f"  AWAITING CONFIRMATION (not counted yet): entries {a.pending}")
        if a.disputed:
            lines.append(f"  DISPUTED (not counted yet): entries {a.disputed}")
        for msg in a.anomalies:
            lines.append(f"  ! {msg}")
    return "\n".join(lines)
