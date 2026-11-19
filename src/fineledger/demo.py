"""A realistic scenario, built through the public API only (no back doors).

build_scenario() seeds a workshop history; main() then walks the story a judge cares about.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import date, datetime, time, timedelta

from . import intake
from .accounts import statement
from .agents import occasion, payments, runner, wastage
from .agents.reconcile import diff_statements, propose_settlement
from .agents.trust import export_passport
from .gold import fmt_mg, to_mg
from .ledger import Ledger

KEYS = {"J1": "demo-key-J1", "K1": "demo-key-K1", "K2": "demo-key-K2", "L1": "demo-key-L1"}


def at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour))


def _both(L: Ledger, rec, other: str, ts=None):
    L.confirm(rec.seq, other, KEYS[other], ts)


def _closed_order(L, oid, jw, kg, design, start: date, days: int, gross_g: str, loss_bp: int,
                  labour_rupees: int, paid_after: int | None, on_time=True, agreed_bp=300, scrap_g=None):
    delivered = start + timedelta(days=days)
    due = delivered if on_time else delivered - timedelta(days=2)
    L.open_order(oid, jw, kg, design, due.isoformat(), labour_rupees * 100, ts=at(start, 9))
    gross = to_mg(gross_g)
    iss = L.record_entry("ISSUE", oid, jw, KEYS[jw], gross_mg=gross, fineness=916, wastage_bp=agreed_bp, ts=at(start))
    _both(L, iss, kg, at(start, 11))
    ret_gross = gross * (10000 - loss_bp) // 10000
    ret = L.record_entry("RETURN", oid, kg, KEYS[kg], gross_mg=ret_gross, fineness=916, final=True, ts=at(delivered))
    _both(L, ret, jw, at(delivered, 11))
    if scrap_g:
        sc = L.record_entry("SCRAP", oid, kg, KEYS[kg], gross_mg=to_mg(scrap_g), fineness=916, ts=at(delivered, 12))
        _both(L, sc, jw, at(delivered, 13))
    if paid_after is not None:
        pay = L.record_entry("PAYMENT", oid, jw, KEYS[jw], amount_paise=labour_rupees * 100, ts=at(delivered + timedelta(days=paid_after)))
        _both(L, pay, kg, at(delivered + timedelta(days=paid_after), 15))
    return iss, ret


def build_scenario(today: date, path: str | None = None) -> Ledger:
    L = Ledger(path)
    L.add_party("J1", "jeweller", "Lakshmi Jewellers", "en", ts=at(today - timedelta(days=200)))
    L.add_party("K1", "karigar", "Murugan", "ta", ts=at(today - timedelta(days=200)))
    L.add_party("K2", "karigar", "Selvam", "hi", ts=at(today - timedelta(days=200)))
    L.add_party("L1", "refiner", "Chennai Refiners", "en", ts=at(today - timedelta(days=200)))
    d = lambda n: today - timedelta(days=n)  # noqa: E731
    # Murugan's history: six chain orders over four months
    _closed_order(L, "O-101", "J1", "K1", "chain", d(120), 6, "35.000", 240, 5000, 2)
    _closed_order(L, "O-102", "J1", "K1", "chain", d(105), 7, "42.500", 255, 5500, 1)
    iss103, _ = _closed_order(L, "O-103", "J1", "K1", "chain", d(90), 6, "28.000", 270, 4200, 4, on_time=False)
    _closed_order(L, "O-104", "J1", "K1", "chain", d(75), 5, "50.000", 250, 6500, 2)
    _closed_order(L, "O-105", "J1", "K1", "chain", d(60), 7, "31.000", 300, 4800, 3)
    _closed_order(L, "O-106", "J1", "K1", "chain", d(40), 6, "38.000", 260, 5200, 2)
    # O-103 was late because the jeweller delivered the gold late: both parties confirmed that note
    note = L.record_entry("DELAY_NOTE", "O-103", "K1", KEYS["K1"], cause="jeweller",
                          note="gold issued 2 days after the agreed date", ts=at(d(88)))
    _both(L, note, "J1", at(d(88), 12))
    # Selvam is faster on chains
    for i, (st, days) in enumerate([(100, 3), (80, 3), (55, 4)], start=1):
        _closed_order(L, f"O-30{i}", "J1", "K2", "chain", d(st), days, "20.000", 250, 3000, 1)
    # O-202: delivered 11 days ago, high loss, labour still unpaid
    _closed_order(L, "O-202", "J1", "K1", "chain", d(17), 6, "30.000", 633, 6000, None, scrap_g="0.300")
    # O-203: a second order Murugan has open right now
    L.open_order("O-203", "J1", "K1", "ring", (today + timedelta(days=10)).isoformat(), 300000, ts=at(d(2), 9))
    r203 = L.record_entry("ISSUE", "O-203", "J1", KEYS["J1"], gross_mg=to_mg("12.000"), fineness=916,
                          wastage_bp=300, ts=at(d(1)))
    _both(L, r203, "K1", at(d(1), 12))
    return L


def h(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main(today: date | None = None) -> int:
    today = today or date.today()
    tmpdir = tempfile.mkdtemp(prefix="fineledger-")
    path = os.path.join(tmpdir, "ledger.jsonl")
    L = build_scenario(today, path)
    print(f"FineLedger demo | today = {today} | ledger file = {path}")
    print(f"Seeded: {len(L.records)} chained records covering 10 closed orders and 2 open ones.")

    h("1. WASTAGE AGENT: a new chain order for Murugan. What should we agree?")
    prop = wastage.propose(L, "K1", "chain")
    print(prop.summary)

    h("2. INTAKE: Lakshmi Jewellers sends a WhatsApp message (2 days ago)")
    msg = "issue 40.000g 22K order O-201 wastage 2.6%"
    L.open_order("O-201", "J1", "K1", "chain", (today + timedelta(days=3)).isoformat(), 520000, ts=at(today - timedelta(days=2), 9))
    p = intake.parse(msg)
    issue = L.record_entry(p.kind, p.order_id, "J1", KEYS["J1"], gross_mg=p.gross_mg, fineness=p.fineness,
                           wastage_bp=p.wastage_bp, ts=at(today - timedelta(days=2)))
    print(f'  message : "{msg}"')
    print(f"  parsed  : {p.kind} {fmt_mg(p.gross_mg)} @ {p.fineness} = {fmt_mg(issue.data['fine_mg'])} fine gold, wastage {p.wastage_bp} bp")
    print(f"  status  : {L.status(issue.seq)} (needs Murugan's confirmation before it counts)")
    for bad in ("issue ten grams order O-201", "issue 10.2504g 22K order O-201 wastage 2%"):
        try:
            intake.parse(bad)
        except intake.ParseError as e:
            print(f'  rejected "{bad}" -> {e}')

    h("3. AGENT LOOP: what the agents do right now")
    now = datetime.combine(today, time(9, 0))
    for m in runner.run_agents(L, now):
        print(f"  -> {m.to} [{m.lang}] ({m.kind}) {m.text}")
    ras = occasion.suggest_reassign(L, "O-201", today)
    print(f"  reassignment options for O-201 (needs jeweller approval): {ras or 'none can make the date'}")

    h("4. KARIGAR CONFIRMS (reply '1' on WhatsApp)")
    L.confirm(issue.seq, "K1", KEYS["K1"], now)
    print(f"  entry {issue.seq} is now {L.status(issue.seq)}")

    h("5. 'THE JEWELLER'S NUMBER DIFFERS FROM MINE': diff two notebooks")
    jw_book = [{"date": "2026-10-02", "kind": "ISSUE", "grams": "25.000"}, {"date": "2026-10-09", "kind": "RETURN", "grams": "24.100"},
               {"date": "2026-10-12", "kind": "ISSUE", "grams": "15.500"}, {"date": "2026-10-20", "kind": "RETURN", "grams": "14.900"}]
    kg_book = [{"date": "2026-10-02", "kind": "ISSUE", "grams": "25.000"}, {"date": "2026-10-09", "kind": "RETURN", "grams": "24.400"},
               {"date": "2026-10-20", "kind": "RETURN", "grams": "14.900"}, {"date": "2026-10-27", "kind": "SCRAP", "grams": "0.450"}]
    df = diff_statements(jw_book, kg_book)
    print(f"  {df['summary']}")
    for m in df["weight_mismatch"]:
        print(f"  differs : {m['a']['date']} {m['a']['kind']}  jeweller {m['a']['grams']} g vs karigar {m['b']['grams']} g  (delta {fmt_mg(m['delta_mg'])})")
    for r in df["only_in_a"]:
        print(f"  only jeweller has: {r['date']} {r['kind']} {r['grams']} g")
    for r in df["only_in_b"]:
        print(f"  only karigar has : {r['date']} {r['kind']} {r['grams']} g")

    h("6. RECONCILIATION: settlement drafted from CONFIRMED entries, approved by BOTH")
    s = propose_settlement(L, "J1", "K1", ts=now)
    for line in s.data["explanation"]:
        print(f"  {line}")
    print(f"  blocked (unconfirmed entries): {[b['order'] for b in s.data['blocked_orders']] or 'none'}")
    print(f"  status : {L.settlement_status(s.seq)['status']}, awaiting {L.settlement_status(s.seq)['awaiting']}")
    L.approve_settlement(s.seq, "K1", KEYS["K1"], now)
    print(f"  after Murugan approves : {L.settlement_status(s.seq)['status']}, awaiting {L.settlement_status(s.seq)['awaiting']}")
    L.approve_settlement(s.seq, "J1", KEYS["J1"], now)
    print(f"  after Lakshmi approves : {L.settlement_status(s.seq)['status']}")

    h("7. PAYER RECORD: jewellers are visible too")
    print(f"  Lakshmi Jewellers: {payments.jeweller_record(L, 'J1')}")

    h("8. TAMPER TEST: change one weight in the ledger file")
    bad = os.path.join(tmpdir, "tampered.jsonl")
    shutil.copy(path, bad)
    lines = open(bad, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(lines):
        rec = json.loads(ln)
        if rec["rtype"] == "entry" and rec["data"]["kind"] == "RETURN" and rec["data"]["order_id"] == "O-202":
            rec["data"]["gross_mg"] += 500
            lines[i] = json.dumps(rec, ensure_ascii=False)
            break
    open(bad, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    ok, err = Ledger(bad, verify_on_load=False).verify()
    print(f"  original ledger verifies: {L.verify()[0]}")
    print(f"  tampered ledger verifies: {ok}  ->  {err}")
    print(f"  signatures all valid    : {not L.verify_signatures(KEYS)}")

    h("9. TRUST PASSPORT: owned by the karigar, shared only with consent")
    try:
        export_passport(L, "K1", "L1")
    except PermissionError as e:
        print(f"  before consent: refused ({e})")
    L.set_consent("K1", "L1", True, KEYS["K1"], ts=now)
    print("  after consent :", json.dumps(export_passport(L, "K1", "L1"), indent=2))

    h("10. THE KARIGAR'S OWN STATEMENT (full access, always)")
    print(statement(L, "K1", "J1"))
    ok, err = L.verify()
    print(f"\nLedger integrity: {'OK' if ok else err} ({len(L.records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
