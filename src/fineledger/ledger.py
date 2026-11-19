"""Append-only, hash-chained, countersigned ledger.

Nothing is ever edited. A correction is a new REVERSAL entry that both parties
confirm. An entry only counts toward anyone's balance once BOTH the jeweller and
the karigar have confirmed it and neither has an open dispute on it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime

from .gold import fine_mg

GENESIS = "0" * 64
GOLD_KINDS = {"ISSUE", "RETURN", "SCRAP", "RECOVERY"}
ENTRY_KINDS = GOLD_KINDS | {"PAYMENT", "DELAY_NOTE", "REVERSAL"}
CAUSES = {"jeweller", "karigar", "customer", "other"}


class LedgerError(ValueError):
    pass


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(body: dict) -> str:
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def _sign(key: str, text: str) -> str:
    return hmac.new(key.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Record:
    seq: int
    rtype: str
    data: dict
    ts: str
    prev: str
    hash: str

    def body(self) -> dict:
        return {"seq": self.seq, "rtype": self.rtype, "data": self.data, "ts": self.ts, "prev": self.prev}


class Ledger:
    def __init__(self, path: str | None = None, verify_on_load: bool = True):
        self.path = str(path) if path else None
        self.records: list[Record] = []
        self._parties: dict[str, dict] = {}
        self._orders: dict[str, dict] = {}
        self._entry_seqs: list[int] = []
        self._confirm: dict[tuple[int, str], int] = {}
        self._disputes: list[tuple[int, int, str]] = []
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = Record(**json.loads(line))
                        self.records.append(rec)
                        self._index(rec)
            if verify_on_load:
                ok, err = self.verify()
                if not ok:
                    raise LedgerError(f"ledger failed verification: {err}")

    # ---------- chain mechanics ----------
    def _index(self, rec: Record) -> None:
        d = rec.data
        if rec.rtype == "party":
            self._parties[d["id"]] = d
        elif rec.rtype == "order":
            self._orders[d["order_id"]] = d
        elif rec.rtype == "entry":
            self._entry_seqs.append(rec.seq)
        elif rec.rtype == "confirm":
            self._confirm[(d["ref"], d["party"])] = rec.seq
        elif rec.rtype == "dispute":
            self._disputes.append((rec.seq, d["ref"], d["party"]))

    def _append(self, rtype: str, data: dict, ts: datetime | None = None) -> Record:
        stamp = (ts or datetime.now()).replace(microsecond=0).isoformat()
        seq = len(self.records) + 1
        prev = self.records[-1].hash if self.records else GENESIS
        body = {"seq": seq, "rtype": rtype, "data": data, "ts": stamp, "prev": prev}
        rec = Record(seq, rtype, data, stamp, prev, _hash(body))
        self.records.append(rec)
        self._index(rec)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        return rec

    def verify(self) -> tuple[bool, str | None]:
        prev = GENESIS
        for i, rec in enumerate(self.records, start=1):
            if rec.seq != i:
                return False, f"record {i}: sequence broken"
            if rec.prev != prev:
                return False, f"record {i}: link to previous record broken"
            if _hash(rec.body()) != rec.hash:
                return False, f"record {i}: contents do not match their hash (tampered)"
            prev = rec.hash
        return True, None

    def verify_signatures(self, keyring: dict[str, str]) -> list[int]:
        """Return seqs of confirm/approve records whose signature does not check out."""
        bad = []
        for r in self.records:
            if r.rtype in ("confirm", "approve"):
                key = keyring.get(r.data["party"])
                target = self.records[r.data["ref"] - 1].hash
                if key is None or not hmac.compare_digest(_sign(key, target), r.data["sig"]):
                    bad.append(r.seq)
        return bad

    # ---------- registry ----------
    def add_party(self, pid: str, role: str, name: str = "", lang: str = "en", ts=None) -> Record:
        if role not in ("jeweller", "karigar", "refiner"):
            raise LedgerError("role must be jeweller, karigar or refiner")
        return self._append("party", {"id": pid, "role": role, "name": name or pid, "lang": lang}, ts)

    def party(self, pid: str) -> dict:
        if pid not in self._parties:
            raise LedgerError(f"unknown party {pid}")
        return self._parties[pid]

    def open_order(self, order_id, jeweller, karigar, design, due: str, labour_paise: int, ts=None) -> Record:
        if order_id in self._orders:
            raise LedgerError(f"order {order_id} already exists")
        if self.party(jeweller)["role"] != "jeweller" or self.party(karigar)["role"] != "karigar":
            raise LedgerError("order needs a jeweller and a karigar")
        return self._append("order", {"order_id": order_id, "jeweller": jeweller, "karigar": karigar,
                                      "design": design, "due": due, "labour_paise": labour_paise}, ts)

    def order(self, order_id: str) -> dict:
        if order_id not in self._orders:
            raise LedgerError(f"unknown order {order_id}")
        return self._orders[order_id]

    def orders(self, karigar: str | None = None, jeweller: str | None = None) -> list[dict]:
        return [o for o in self._orders.values()
                if (karigar is None or o["karigar"] == karigar) and (jeweller is None or o["jeweller"] == jeweller)]

    # ---------- entries ----------
    def record_entry(self, kind: str, order_id: str, by: str, key: str, *, gross_mg: int | None = None,
                     fineness: int | None = None, amount_paise: int | None = None, wastage_bp: int | None = None,
                     final: bool = False, evidence: str | None = None, reverses: int | None = None,
                     cause: str | None = None, note: str = "", ts=None) -> Record:
        if kind not in ENTRY_KINDS:
            raise LedgerError(f"unknown entry kind {kind}")
        o = self.order(order_id)
        if by not in (o["jeweller"], o["karigar"]):
            raise LedgerError(f"{by} is not a party to order {order_id}")
        d = {"kind": kind, "order_id": order_id, "jeweller": o["jeweller"], "karigar": o["karigar"],
             "by": by, "note": note}
        if kind in GOLD_KINDS:
            if not gross_mg or gross_mg <= 0 or not fineness:
                raise LedgerError(f"{kind} needs a positive weight and a purity")
            d.update(gross_mg=gross_mg, fineness=fineness, fine_mg=fine_mg(gross_mg, fineness), evidence=evidence)
            if kind == "ISSUE":
                if wastage_bp is None or wastage_bp < 0:
                    raise LedgerError("ISSUE must record the agreed wastage (basis points)")
                d["wastage_bp"] = wastage_bp
            if kind == "RETURN":
                d["final"] = bool(final)
        elif kind == "PAYMENT":
            if not amount_paise or amount_paise <= 0:
                raise LedgerError("PAYMENT needs a positive amount")
            d["amount_paise"] = amount_paise
        elif kind == "DELAY_NOTE":
            if cause not in CAUSES:
                raise LedgerError(f"cause must be one of {sorted(CAUSES)}")
            d["cause"] = cause
        elif kind == "REVERSAL":
            if not reverses or reverses not in self._entry_seqs:
                raise LedgerError("REVERSAL must point at an existing entry")
            if self.records[reverses - 1].data["order_id"] != order_id:
                raise LedgerError("REVERSAL must stay within the same order")
            d["reverses"] = reverses
        rec = self._append("entry", d, ts)
        self._confirm_as(rec.seq, by, key, ts)  # the recorder signs their own entry
        return rec

    def _entry(self, seq: int) -> Record:
        if seq not in self._entry_seqs:
            raise LedgerError(f"record {seq} is not an entry")
        return self.records[seq - 1]

    def _confirm_as(self, seq: int, party: str, key: str, ts=None) -> Record:
        e = self._entry(seq)
        if party not in (e.data["jeweller"], e.data["karigar"]):
            raise LedgerError(f"{party} is not a party to entry {seq}")
        return self._append("confirm", {"ref": seq, "party": party, "sig": _sign(key, e.hash)}, ts)

    def confirm(self, seq: int, party: str, key: str, ts=None) -> Record:
        if self.status(seq) == "confirmed":
            raise LedgerError(f"entry {seq} is already confirmed by both parties")
        if (seq, party) in self._confirm and not self._has_open_dispute(seq, party):
            raise LedgerError(f"{party} has already confirmed entry {seq}")
        return self._confirm_as(seq, party, key, ts)

    def dispute(self, seq: int, party: str, reason: str, ts=None) -> Record:
        e = self._entry(seq)
        if party not in (e.data["jeweller"], e.data["karigar"]):
            raise LedgerError(f"{party} is not a party to entry {seq}")
        return self._append("dispute", {"ref": seq, "party": party, "reason": reason}, ts)

    def _has_open_dispute(self, seq: int, party: str) -> bool:
        return any(e == seq and p == party and self._confirm.get((seq, p), 0) < d for d, e, p in self._disputes)

    def status(self, seq: int) -> str:
        e = self._entry(seq)
        parties = (e.data["jeweller"], e.data["karigar"])
        if any(self._has_open_dispute(seq, p) for p in parties):
            return "disputed"
        return "confirmed" if all((seq, p) in self._confirm for p in parties) else "pending"

    def entries(self, order_id=None, karigar=None, kind=None, status=None) -> list[Record]:
        out = []
        for s in self._entry_seqs:
            r = self.records[s - 1]
            if order_id and r.data["order_id"] != order_id:
                continue
            if karigar and r.data["karigar"] != karigar:
                continue
            if kind and r.data["kind"] != kind:
                continue
            if status and self.status(s) != status:
                continue
            out.append(r)
        return out

    def effective(self, order_id=None, karigar=None) -> list[Record]:
        """Fully confirmed, undisputed entries that have not been reversed."""
        confirmed = self.entries(order_id=order_id, karigar=karigar, status="confirmed")
        voided = {r.data["reverses"] for r in confirmed if r.data["kind"] == "REVERSAL"}
        return [r for r in confirmed if r.seq not in voided]

    # ---------- settlement / consent records ----------
    def add_settlement(self, data: dict, ts=None) -> Record:
        return self._append("settlement", data, ts)

    def approve_settlement(self, seq: int, party: str, key: str, ts=None) -> Record:
        s = self.records[seq - 1]
        if s.rtype != "settlement":
            raise LedgerError(f"record {seq} is not a settlement")
        if party not in (s.data["jeweller"], s.data["karigar"]):
            raise LedgerError("only the jeweller or the karigar can approve a settlement")
        if any(r.rtype == "approve" and r.data["ref"] == seq and r.data["party"] == party for r in self.records):
            raise LedgerError(f"{party} already approved settlement {seq}")
        return self._append("approve", {"ref": seq, "party": party, "sig": _sign(key, s.hash)}, ts)

    def reject_settlement(self, seq: int, party: str, reason: str, ts=None) -> Record:
        s = self.records[seq - 1]
        if s.rtype != "settlement" or party not in (s.data["jeweller"], s.data["karigar"]):
            raise LedgerError("cannot reject this settlement")
        return self._append("reject", {"ref": seq, "party": party, "reason": reason}, ts)

    def settlement_status(self, seq: int) -> dict:
        s = self.records[seq - 1]
        need = {s.data["jeweller"], s.data["karigar"]}
        got = {r.data["party"] for r in self.records if r.rtype == "approve" and r.data["ref"] == seq}
        rejected = [r.data["party"] for r in self.records if r.rtype == "reject" and r.data["ref"] == seq]
        status = "rejected" if rejected else ("approved" if got == need else "awaiting")
        return {"status": status, "approved_by": sorted(got), "awaiting": sorted(need - got), "rejected_by": rejected}

    def set_consent(self, karigar: str, grantee: str, granted: bool, key: str, scope: str = "passport", ts=None) -> Record:
        payload = {"karigar": karigar, "grantee": grantee, "granted": bool(granted), "scope": scope}
        return self._append("consent", {**payload, "sig": _sign(key, _canon(payload))}, ts)

    def has_consent(self, karigar: str, grantee: str, scope: str = "passport") -> bool:
        state = False
        for r in self.records:
            d = r.data
            if r.rtype == "consent" and d["karigar"] == karigar and d["grantee"] == grantee and d["scope"] == scope:
                state = d["granted"]
        return state
