"""Thin HTTP layer. Auth here is a per-party API key (DEMO). In production this is
replaced by WhatsApp-verified identity + OTP and per-party signing keys on the device.
"""
from __future__ import annotations

import hmac
from datetime import datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import intake
from .accounts import account, karigar_accounts, statement
from .agents import runner
from .agents.trust import export_passport, passport
from .gold import fineness_of, to_mg
from .ledger import Ledger, LedgerError


class OrderIn(BaseModel):
    order_id: str
    karigar: str
    design: str
    due: str
    labour_rupees: int


class EntryIn(BaseModel):
    kind: str
    order_id: str
    grams: str | None = None
    purity: str | None = None
    rupees: int | None = None
    wastage_percent: str | None = None
    final: bool = False
    cause: str | None = None
    reverses: int | None = None
    note: str = ""


class IntakeIn(BaseModel):
    text: str


class ConsentIn(BaseModel):
    grantee: str
    granted: bool


class ReasonIn(BaseModel):
    reason: str


def create_app(ledger: Ledger, keys: dict[str, str]) -> FastAPI:
    app = FastAPI(title="FineLedger API", version="0.1.0")

    def who(x_party_id: str = Header(...), x_party_key: str = Header(...)) -> str:
        key = keys.get(x_party_id)
        if key is None or not hmac.compare_digest(key, x_party_key):
            raise HTTPException(401, "bad party id or key")
        return x_party_id

    def ok(fn):
        try:
            return fn()
        except (LedgerError, ValueError, KeyError) as e:
            raise HTTPException(422, str(e)) from e

    def record(party: str, e: EntryIn):
        kw = dict(final=e.final, cause=e.cause, reverses=e.reverses, note=e.note)
        if e.grams:
            kw["gross_mg"] = to_mg(e.grams)
            kw["fineness"] = fineness_of(e.purity or "")
        if e.rupees:
            kw["amount_paise"] = e.rupees * 100
        if e.wastage_percent is not None:
            kw["wastage_bp"] = int(Decimal(e.wastage_percent) * 100)
        return ledger.record_entry(e.kind.upper(), e.order_id, party, keys[party], **kw)

    @app.post("/orders")
    def open_order(o: OrderIn, party: str = Depends(who)):
        if ledger.party(party)["role"] != "jeweller":
            raise HTTPException(403, "only a jeweller opens an order")
        r = ok(lambda: ledger.open_order(o.order_id, party, o.karigar, o.design, o.due, o.labour_rupees * 100))
        return {"seq": r.seq}

    @app.post("/entries")
    def add_entry(e: EntryIn, party: str = Depends(who)):
        r = ok(lambda: record(party, e))
        return {"seq": r.seq, "status": ledger.status(r.seq), "fine_mg": r.data.get("fine_mg")}

    @app.post("/intake")
    def from_message(m: IntakeIn, party: str = Depends(who)):
        try:
            p = intake.parse(m.text)
        except intake.ParseError as e:
            raise HTTPException(422, str(e)) from e
        kw = {k: v for k, v in dict(gross_mg=p.gross_mg, fineness=p.fineness, amount_paise=p.amount_paise,
                                    wastage_bp=p.wastage_bp, final=p.final).items() if v not in (None, False)}
        r = ok(lambda: ledger.record_entry(p.kind, p.order_id, party, keys[party], **kw))
        return {"seq": r.seq, "status": ledger.status(r.seq), "parsed": p.__dict__}

    @app.post("/entries/{seq}/confirm")
    def confirm(seq: int, party: str = Depends(who)):
        r = ok(lambda: ledger.confirm(seq, party, keys[party]))
        return {"status": ledger.status(seq), "signed_by": r.data["party"]}

    @app.post("/entries/{seq}/dispute")
    def dispute(seq: int, body: ReasonIn, party: str = Depends(who)):
        ok(lambda: ledger.dispute(seq, party, body.reason))
        return {"status": ledger.status(seq)}

    @app.get("/orders/{order_id}/account")
    def order_account(order_id: str, party: str = Depends(who)):
        o = ok(lambda: ledger.order(order_id))
        if party not in (o["jeweller"], o["karigar"]):
            raise HTTPException(403, "not your order")
        return account(ledger, order_id).to_dict()

    @app.get("/karigars/{kid}/account")
    def karigar_account(kid: str, party: str = Depends(who)):
        role = ledger.party(party)["role"]
        if party == kid:
            accts = karigar_accounts(ledger, kid)  # full access to his own account
        elif role == "jeweller":
            accts = karigar_accounts(ledger, kid, jeweller=party)  # a jeweller sees only their own orders
        else:
            raise HTTPException(403, "not your account")
        return {"orders": [a.to_dict() for a in accts],
                "statement": statement(ledger, kid, None if party == kid else party)}

    @app.post("/karigars/{kid}/consent")
    def consent(kid: str, c: ConsentIn, party: str = Depends(who)):
        if party != kid:
            raise HTTPException(403, "only the karigar controls sharing of his passport")
        ledger.set_consent(kid, c.grantee, c.granted, keys[kid])
        return {"granted": c.granted, "grantee": c.grantee}

    @app.get("/karigars/{kid}/passport")
    def get_passport(kid: str, party: str = Depends(who)):
        if party == kid:
            return passport(ledger, kid)
        try:
            return export_passport(ledger, kid, party)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e

    @app.post("/agents/run")
    def run_agents(party: str = Depends(who)):
        msgs = runner.run_agents(ledger, datetime.now())
        return [m.__dict__ for m in msgs if m.to == party]

    @app.get("/ledger/verify")
    def verify(party: str = Depends(who)):
        good, err = ledger.verify()
        return {"intact": good, "error": err, "records": len(ledger.records),
                "bad_signatures": ledger.verify_signatures(keys)}

    return app
