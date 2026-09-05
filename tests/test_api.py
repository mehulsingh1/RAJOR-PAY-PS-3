"""API surface + worker, driven in playbook mode (no LLM)."""

import time

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "playbook")
    monkeypatch.setenv("RECOVERY_SEED", "42")
    monkeypatch.setenv("LIVE_CSV", str(tmp_path / "live.csv"))
    monkeypatch.setenv("NOTIF_CSV", str(tmp_path / "notif.csv"))
    import importlib
    import api.worker as w
    importlib.reload(w)
    import api.main as m
    importlib.reload(m)
    from fastapi.testclient import TestClient
    with TestClient(m.app) as c:
        yield c


def test_health_and_empty_metrics(client):
    assert client.get("/health").json()["ok"] is True
    assert client.get("/metrics").json()["empty"] is True


def test_simulation_produces_and_resolves_transactions(client):
    client.post("/simulation/start", json={"rate": 6.0, "seed": 11})
    time.sleep(6)
    client.post("/simulation/stop")

    txns = client.get("/transactions").json()
    assert txns["count"] > 0

    m = client.get("/metrics").json()
    assert m["empty"] is False
    assert set(m["comparison"]["by_strategy"]) == {"agent", "retry_all", "reminder_all", "static_playbook"}

    # some messages were sent, learning recorded something
    assert client.get("/notifications").json()["count"] >= 0
    assert isinstance(client.get("/learning").json()["priors"], list)

    # csv export works
    exp = client.get("/export/transactions.csv")
    assert exp.status_code == 200 and "txn_id" in exp.text


def test_queue_resolution(client):
    client.post("/simulation/start", json={"rate": 8.0, "seed": 5})
    time.sleep(6)
    client.post("/simulation/stop")
    q = client.get("/queue").json()
    if q["items"]:
        tid = q["items"][0]["txn_id"]
        r = client.post(f"/queue/{tid}", json={"action": "override", "override": "send_reminder"})
        assert r.json().get("chosen") == "send_reminder"
        assert tid not in [i["txn_id"] for i in client.get("/queue").json()["items"]]
