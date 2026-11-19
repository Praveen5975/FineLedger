import pytest
from fastapi.testclient import TestClient

from fineledger.api import create_app


@pytest.fixture
def client(scenario, keys):
    return TestClient(create_app(scenario, keys)), keys


def H(keys, who):
    return {"X-Party-Id": who, "X-Party-Key": keys[who]}


def test_auth_required(client):
    c, keys = client
    assert c.get("/ledger/verify").status_code == 422
    assert c.get("/ledger/verify", headers={"X-Party-Id": "K1", "X-Party-Key": "nope"}).status_code == 401


def test_full_two_party_flow_over_http(client):
    c, keys = client
    r = c.post("/orders", headers=H(keys, "J1"), json={"order_id": "O-500", "karigar": "K1", "design": "chain",
                                                       "due": "2026-12-20", "labour_rupees": 4000})
    assert r.status_code == 200
    r = c.post("/intake", headers=H(keys, "J1"), json={"text": "issue 20.000g 22K order O-500 wastage 2.6%"})
    seq = r.json()["seq"]
    assert r.json()["status"] == "pending"
    assert c.post(f"/entries/{seq}/confirm", headers=H(keys, "K1")).json()["status"] == "confirmed"
    assert c.post(f"/entries/{seq}/confirm", headers=H(keys, "K1")).status_code == 422  # no double signing
    assert c.get("/ledger/verify", headers=H(keys, "K1")).json()["intact"] is True


def test_bad_message_is_rejected_with_a_helpful_reason(client):
    c, keys = client
    r = c.post("/intake", headers=H(keys, "J1"), json={"text": "issue some gold order O-203"})
    assert r.status_code == 422 and "weight" in r.json()["detail"].lower()


def test_karigar_sees_everything_of_his_own_but_not_others(client):
    c, keys = client
    own = c.get("/karigars/K1/account", headers=H(keys, "K1"))
    assert own.status_code == 200 and len(own.json()["orders"]) >= 8
    assert c.get("/karigars/K1/account", headers=H(keys, "K2")).status_code == 403
    assert c.get("/orders/O-202/account", headers=H(keys, "K2")).status_code == 403


def test_only_the_karigar_controls_his_passport(client):
    c, keys = client
    assert c.get("/karigars/K1/passport", headers=H(keys, "L1")).status_code == 403
    assert c.post("/karigars/K1/consent", headers=H(keys, "L1"), json={"grantee": "L1", "granted": True}).status_code == 403
    assert c.post("/karigars/K1/consent", headers=H(keys, "K1"), json={"grantee": "L1", "granted": True}).status_code == 200
    assert c.get("/karigars/K1/passport", headers=H(keys, "L1")).json()["orders_delivered"] == 7


def test_agents_endpoint_only_returns_your_own_messages(client):
    c, keys = client
    msgs = c.post("/agents/run", headers=H(keys, "K2")).json()
    assert all(m["to"] == "K2" for m in msgs)
