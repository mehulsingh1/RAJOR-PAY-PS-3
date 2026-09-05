"""AGENT_MODE=playbook runs the full pipeline without the LLM."""

import importlib
import os

import pytest


@pytest.fixture
def playbook_graph(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "playbook")
    monkeypatch.setenv("RECOVERY_SEED", "42")
    import graph.nodes as nodes
    importlib.reload(nodes)
    from notifications.outbox import Outbox
    nodes.set_outbox(Outbox(path=str(tmp_path / "n.csv")))
    import graph.build_graph as bg
    importlib.reload(bg)
    yield bg.build_graph()
    monkeypatch.delenv("AGENT_MODE", raising=False)
    importlib.reload(nodes)
    importlib.reload(bg)


def _state(txn):
    return {"txn": txn, "risk_score": 0.0, "risk_tier": "", "risk_reason": "",
            "expected_recoverable": 0.0, "diagnosis": "", "rag_context": "",
            "decision": "", "decision_reasoning": "", "decision_overridden": False,
            "stop_reason": None, "compliance_notes": [], "notifications": [],
            "ptp": None, "action_result": {}, "audit_log": []}


def test_playbook_picks_kb_action_no_llm(playbook_graph):
    txn = {"txn_id": "t1", "amount": 1000.0, "failure_code": "mandate_lapsed",
           "failure_stage": "subscription_failure", "payment_method": "mandate",
           "retry_count": 0, "customer_segment": "regular", "do_not_contact": False,
           "preferred_language": "en", "days_overdue": None}
    out = playbook_graph.invoke(_state(txn), config={"recursion_limit": 40})
    assert out["decision"] == "request_mandate_renewal"
    assert "playbook" in out["decision_reasoning"].lower()


def test_playbook_still_enforces_compliance(playbook_graph):
    txn = {"txn_id": "t2", "amount": 90000.0, "failure_code": "invoice_unpaid",
           "failure_stage": "receivable_overdue", "payment_method": "netbanking",
           "retry_count": 0, "customer_segment": "high_value", "do_not_contact": True,
           "preferred_language": "hinglish", "days_overdue": 70}
    out = playbook_graph.invoke(_state(txn), config={"recursion_limit": 40})
    assert out["stop_reason"] == "do_not_contact_flag"
