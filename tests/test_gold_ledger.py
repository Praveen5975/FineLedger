import json

import pytest

from fineledger.gold import fine_mg, fineness_of, fmt_mg, to_mg
from fineledger.ledger import Ledger, LedgerError


def mini(path=None):
    L = Ledger(path)
    L.add_party("J", "jeweller", "Jeweller")
    L.add_party("K", "karigar", "Karigar")
    L.open_order("O1", "J", "K", "chain", "2026-12-01", 100000)
    return L


def test_milligram_precision_and_fine_gold():
    assert to_mg("10.250") == 10250
    assert fine_mg(to_mg("10.000"), 916) == 9160
    assert fineness_of("22K") == 916 and fineness_of("916") == 916
    assert fmt_mg(9160) == "9.160 g" and fmt_mg(-5) == "-0.005 g"
    with pytest.raises(ValueError):
        to_mg("10.2504")  # finer than 1 mg is rejected, never silently rounded
    with pytest.raises(ValueError):
        to_mg("-1")


def test_rounding_is_half_even_and_deterministic():
    assert fine_mg(1, 500) == 0   # 0.5 -> 0 (even)
    assert fine_mg(3, 500) == 2   # 1.5 -> 2 (even)


def test_entry_needs_both_parties_before_it_counts():
    L = mini()
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    assert L.status(e.seq) == "pending" and L.effective(order_id="O1") == []
    L.confirm(e.seq, "K", "kk")
    assert L.status(e.seq) == "confirmed" and len(L.effective(order_id="O1")) == 1


def test_outsider_cannot_record_or_confirm():
    L = mini()
    L.add_party("X", "jeweller", "Other")
    with pytest.raises(LedgerError):
        L.record_entry("ISSUE", "O1", "X", "kx", gross_mg=1000, fineness=916, wastage_bp=0)
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=1000, fineness=916, wastage_bp=0)
    with pytest.raises(LedgerError):
        L.confirm(e.seq, "X", "kx")


def test_issue_must_state_wastage():
    L = mini()
    with pytest.raises(LedgerError):
        L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=1000, fineness=916)


def test_dispute_blocks_until_reconfirmed():
    L = mini()
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    L.confirm(e.seq, "K", "kk")
    L.dispute(e.seq, "K", "scale showed 9.900")
    assert L.status(e.seq) == "disputed" and L.effective(order_id="O1") == []
    L.confirm(e.seq, "K", "kk")
    assert L.status(e.seq) == "confirmed"


def test_reversal_voids_an_entry_without_editing_history():
    L = mini()
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    L.confirm(e.seq, "K", "kk")
    r = L.record_entry("REVERSAL", "O1", "J", "kj", reverses=e.seq)
    L.confirm(r.seq, "K", "kk")
    assert "ISSUE" not in [x.data["kind"] for x in L.effective(order_id="O1")]
    assert L.records[e.seq - 1].data["gross_mg"] == 10000  # original is still there
    assert L.verify()[0]


def test_hash_chain_detects_in_memory_tampering():
    L = mini()
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    assert L.verify()[0]
    L.records[e.seq - 1].data["gross_mg"] = 9000
    ok, err = L.verify()
    assert not ok and f"record {e.seq}" in err


def test_persistence_roundtrip_and_file_tampering(tmp_path):
    p = tmp_path / "l.jsonl"
    L = mini(str(p))
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    L.confirm(e.seq, "K", "kk")
    assert len(Ledger(str(p)).records) == len(L.records)
    lines = p.read_text().splitlines()
    rec = json.loads(lines[3])
    rec["data"]["gross_mg"] = 1
    lines[3] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerError):
        Ledger(str(p))


def test_deleting_a_record_breaks_the_chain(tmp_path):
    p = tmp_path / "l.jsonl"
    L = mini(str(p))
    L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    lines = p.read_text().splitlines()
    del lines[2]
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerError):
        Ledger(str(p))


def test_signatures_verify_and_detect_wrong_key():
    L = mini()
    e = L.record_entry("ISSUE", "O1", "J", "kj", gross_mg=10000, fineness=916, wastage_bp=300)
    L.confirm(e.seq, "K", "kk")
    assert L.verify_signatures({"J": "kj", "K": "kk"}) == []
    assert L.verify_signatures({"J": "kj", "K": "WRONG"})  # K's signature fails
