"""Outcome model: mcp_tools/tools.py"""

from mcp_tools.tools import execute_action, _success_probability, ALL_ACTIONS
from tests.conftest import txn


def test_deterministic_for_same_inputs():
    t = txn(failure_code="issuer_timeout")
    assert execute_action("retry", t) == execute_action("retry", t)


def test_probability_bounds():
    for code in ["insufficient_funds", "card_expired", "invoice_unpaid", "mystery_code"]:
        for action in ALL_ACTIONS:
            p = _success_probability(action, txn(failure_code=code))
            assert 0.0 <= p <= 1.0


def test_retry_on_expired_card_is_near_zero():
    assert _success_probability("retry", txn(failure_code="card_expired")) < 0.05


def test_retry_fatigue_decreases_probability():
    p0 = _success_probability("retry", txn(failure_code="issuer_timeout", retry_count=0))
    p2 = _success_probability("retry", txn(failure_code="issuer_timeout", retry_count=2))
    assert p2 < p0


def test_apply_discount_full_recovery_but_margin_cost():
    # discount recovers the full amount; the margin given up shows up as cost
    for i in range(50):
        t = txn(txn_id=f"d{i}", failure_code="user_dropped", amount=1000.0)
        r = execute_action("apply_discount", t)
        if r["success"]:
            assert r["amount_recovered"] == 1000.0
            assert r["intervention_cost"] >= 1000.0 * 0.10
            return
    raise AssertionError("expected at least one discount success in 50 draws")


def test_immediate_retry_is_weak_for_insufficient_funds():
    # brute retry should NOT be a strong play when the money isn't there
    assert _success_probability("retry", txn(failure_code="insufficient_funds")) < 0.25


def test_transient_timeout_retry_stays_strong():
    assert _success_probability("retry", txn(failure_code="issuer_timeout")) > 0.6


def test_unknown_action_is_safe():
    r = execute_action("teleport_money", txn())
    assert r["success"] is False and r["amount_recovered"] == 0.0


def test_kb_smart_policy_beats_naive_baselines():
    import pandas as pd

    rows = pd.read_csv("data/failed_transactions.csv").to_dict(orient="records")
    kb_best = {
        "insufficient_funds": "retry", "bank_decline": "retry",
        "card_expired": "send_reminder", "issuer_timeout": "retry",
        "gateway_timeout": "send_reminder", "otp_timeout": "send_reminder",
        "user_dropped": "apply_discount", "mandate_lapsed": "request_mandate_renewal",
        "invoice_unpaid": "escalate_human",
    }

    def recovered(policy):
        return sum(
            execute_action(policy(r), r)["amount_recovered"]
            for r in rows if not r["do_not_contact"]
        )

    smart = recovered(lambda r: kb_best[r["failure_code"]])
    retry_all = recovered(lambda r: "retry")
    assert smart > retry_all * 1.3
