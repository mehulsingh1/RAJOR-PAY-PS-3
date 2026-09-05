"""Intervention cost model: mcp_tools/costs.py"""

from mcp_tools.costs import intervention_cost, DISCOUNT_RATE
from tests.conftest import txn


def test_retry_has_a_flat_cost():
    assert intervention_cost("retry", txn(), success=False) == 3.0


def test_channel_cost_added_for_messages():
    email = intervention_cost("send_reminder", txn(), success=False, channel="email")
    wa = intervention_cost("send_reminder", txn(), success=False, channel="whatsapp")
    assert wa > email >= 0.10


def test_discount_margin_only_charged_on_success():
    t = txn(amount=10000.0)
    lost = intervention_cost("apply_discount", t, success=False)
    won = intervention_cost("apply_discount", t, success=True)
    assert won - lost == 10000.0 * DISCOUNT_RATE


def test_human_escalation_is_the_priciest_action():
    costs = {a: intervention_cost(a, txn(), success=False)
             for a in ["retry", "send_reminder", "escalate_human", "request_mandate_renewal"]}
    assert costs["escalate_human"] == max(costs.values())
