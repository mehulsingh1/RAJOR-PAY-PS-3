"""Detection / prioritization: graph/detection.py"""

from graph.detection import score_transaction, prioritized
from tests.conftest import txn


def test_score_fields_and_range():
    a = score_transaction(txn(amount=2000.0))
    assert 0 <= a["risk_score"] <= 100
    assert a["risk_tier"] in {"high", "medium", "low"}
    assert a["suggested_action"]


def test_expected_recoverable_is_amount_times_best_prob():
    from mcp_tools.tools import _success_probability, ALL_ACTIONS

    t = txn(amount=1234.0, failure_code="issuer_timeout")
    best_p = max(_success_probability(x, t) for x in ALL_ACTIONS)
    assert score_transaction(t)["expected_recoverable"] == round(1234.0 * best_p, 2)


def test_bigger_recoverable_amount_ranks_higher():
    small = txn(txn_id="s", amount=100.0, failure_code="issuer_timeout")
    big = txn(txn_id="b", amount=5000.0, failure_code="issuer_timeout")
    ordered = prioritized([small, big])
    assert ordered[0]["txn_id"] == "b"


def test_high_value_segment_raises_score():
    lo = score_transaction(txn(customer_segment="regular"))["risk_score"]
    hi = score_transaction(txn(customer_segment="high_value"))["risk_score"]
    assert hi > lo


def test_do_not_contact_noted_in_reason():
    assert "do_not_contact" in score_transaction(txn(do_not_contact=True))["risk_reason"]
