from datetime import date, datetime, time

import pytest

from fineledger import intake
from fineledger.accounts import account, statement
from fineledger.agents import occasion, payments, runner, wastage
from fineledger.agents.reconcile import diff_statements, propose_settlement
from fineledger.agents.trust import export_passport, passport
from fineledger.gold import to_mg
from fineledger.ledger import Ledger, LedgerError

TODAY = date(2026, 11, 19)


def test_closed_order_math(scenario):
    a = account(scenario, "O-202")
    # 30.000 g @916 issued = 27.480 g fine; returned 28.1..g gross, 0.300 g scrap
    assert a.issued_mg == 27480 and a.closed
    assert a.loss_mg == a.issued_mg - a.returned_mg - a.scrap_mg
    assert a.excess_mg == a.loss_mg - a.allowed_mg > 0
    assert a.outstanding_paise == 600000


def test_open_order_gold_is_not_counted_as_loss(scenario):
    a = account(scenario, "O-203")
    assert not a.closed and a.loss_mg == 0 and a.excess_mg == 0
    assert a.with_karigar_mg == a.issued_mg > 0
    assert "not a loss" in statement(scenario, "K1")


def test_unconfirmed_entries_never_count(scenario, keys):
    scenario.open_order("O-9", "J1", "K1", "chain", "2026-12-30", 100)
    scenario.record_entry("ISSUE", "O-9", "J1", keys["J1"], gross_mg=5000, fineness=916, wastage_bp=300)
    a = account(scenario, "O-9")
    assert a.issued_mg == 0 and a.pending  # waiting on the karigar, so it counts for nobody


def test_wastage_proposes_from_own_history(scenario):
    p = wastage.propose(scenario, "K1", "chain")
    assert p.details["suggested_bp"] and 240 <= p.details["suggested_bp"] <= 290
    assert len(p.details["samples"]) >= 3


def test_wastage_refuses_to_guess_without_history(scenario):
    p = wastage.propose(scenario, "K1", "necklace")
    assert p.details["suggested_bp"] is None and "No proposal" in p.summary


def test_wastage_flags_outlier_but_not_normal_orders(scenario):
    assert wastage.flag(scenario, "O-202") is not None
    assert wastage.flag(scenario, "O-105") is None


def test_occasion_red_then_green(scenario):
    assert occasion.assess(scenario, "O-203", TODAY).level in ("green", "amber")
    scenario.open_order("O-201", "J1", "K1", "chain", "2026-11-22", 100)
    scenario.record_entry("ISSUE", "O-201", "J1", "x", gross_mg=to_mg("40"), fineness=916, wastage_bp=260,
                          ts=datetime.combine(date(2026, 11, 17), time(10)))
    red = occasion.assess(scenario, "O-201", TODAY)
    assert red.level == "red" and red.details["slack"] < 0
    assert occasion.suggest_reassign(scenario, "O-201", TODAY)[0]["karigar"] == "K2"


def test_payment_alert_after_grace_period(scenario):
    alerts = payments.assess(scenario, TODAY)
    assert [a.subject for a in alerts] == ["O-202"] and alerts[0].level == "red"
    assert payments.assess(scenario, date(2026, 11, 9)) == []  # inside the grace window


def test_diff_statements_finds_each_kind_of_difference():
    a = [{"date": "2026-10-02", "kind": "ISSUE", "grams": "25.000"}, {"date": "2026-10-09", "kind": "RETURN", "grams": "24.100"},
         {"date": "2026-10-12", "kind": "ISSUE", "grams": "15.500"}]
    b = [{"date": "2026-10-02", "kind": "ISSUE", "grams": "25.000"}, {"date": "2026-10-09", "kind": "RETURN", "grams": "24.400"},
         {"date": "2026-10-27", "kind": "SCRAP", "grams": "0.450"}]
    d = diff_statements(a, b)
    assert len(d["matched"]) == 1 and d["weight_mismatch"][0]["delta_mg"] == 300
    assert len(d["only_in_a"]) == 1 and len(d["only_in_b"]) == 1


def test_settlement_needs_both_parties_and_agent_cannot_approve(scenario, keys):
    s = propose_settlement(scenario, "J1", "K1")
    assert s.data["fine_owed_by_karigar_mg"] > 0 and s.data["labour_owed_by_jeweller_paise"] == 600000
    assert scenario.settlement_status(s.seq)["status"] == "awaiting"
    scenario.approve_settlement(s.seq, "K1", keys["K1"])
    assert scenario.settlement_status(s.seq)["status"] == "awaiting"
    with pytest.raises(LedgerError):
        scenario.approve_settlement(s.seq, "L1", keys["L1"])  # a third party cannot
    with pytest.raises(LedgerError):
        scenario.approve_settlement(s.seq, "agent:reconcile", "x")  # nor can the agent
    scenario.approve_settlement(s.seq, "J1", keys["J1"])
    assert scenario.settlement_status(s.seq)["status"] == "approved"


def test_settlement_excludes_orders_with_unconfirmed_entries(scenario, keys):
    e = scenario.entries(order_id="O-202", kind="RETURN")[0]
    scenario.dispute(e.seq, "K1", "scale showed more")
    s = propose_settlement(scenario, "J1", "K1")
    assert "O-202" not in s.data["orders"] and s.data["blocked_orders"][0]["order"] == "O-202"
    assert s.data["fine_owed_by_karigar_mg"] == 0


def test_passport_excuses_jeweller_caused_delay(scenario):
    p = passport(scenario, "K1")
    assert p["late_orders"] == 1 and p["late_excused_jeweller_or_customer"] == 1 and p["on_time_rate"] == 1.0


def test_passport_needs_consent_and_can_be_withdrawn(scenario, keys):
    with pytest.raises(PermissionError):
        export_passport(scenario, "K1", "L1")
    scenario.set_consent("K1", "L1", True, keys["K1"])
    assert export_passport(scenario, "K1", "L1")["orders_delivered"] == 7
    scenario.set_consent("K1", "L1", False, keys["K1"])
    with pytest.raises(PermissionError):
        export_passport(scenario, "K1", "L1")


def test_passport_says_insufficient_data_for_new_karigar(scenario):
    scenario.add_party("K9", "karigar", "New")
    assert passport(scenario, "K9")["band"] == "insufficient data"


def test_intake_parses_and_never_guesses():
    p = intake.parse("return 9.870 g 916 order O-101 final")
    assert p.kind == "RETURN" and p.gross_mg == 9870 and p.final
    assert intake.parse("paid Rs 4,500 order O-1").amount_paise == 450000
    for bad in ("issue ten grams order O-1", "issue 5g order O-1 wastage 2%", "issue 5g 22K order O-1",
                "hello", "issue 5.0005g 22K order O-1 wastage 2%"):
        with pytest.raises(intake.ParseError):
            intake.parse(bad)


def test_scale_check_flags_mismatch():
    assert intake.scale_check(10000, 10000)[0]
    assert not intake.scale_check(10000, 9900)[0]


def test_agent_loop_messages(scenario, keys):
    scenario.open_order("O-201", "J1", "K1", "chain", "2026-11-22", 100)
    scenario.record_entry("ISSUE", "O-201", "J1", keys["J1"], gross_mg=40000, fineness=916, wastage_bp=260,
                          ts=datetime.combine(date(2026, 11, 17), time(10)))
    msgs = runner.run_agents(scenario, datetime.combine(TODAY, time(9)))
    kinds = {(m.to, m.kind) for m in msgs}
    assert ("K1", "confirm_request") in kinds and ("J1", "risk_alert") in kinds
    assert ("K1", "payment_due") in kinds and ("J1", "wastage_flag") in kinds
    tamil = next(m for m in msgs if m.kind == "payment_due" and m.to == "K1")
    assert tamil.lang == "ta" and "₹6,000" in tamil.text
    assert all(m.cites for m in msgs)  # every message points at ledger entries
