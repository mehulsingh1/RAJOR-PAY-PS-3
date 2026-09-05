"""Compliance engine: graph/compliance.py"""

from graph.compliance import pre_action_halt, enforce_action_compliance, retry_cap
from tests.conftest import txn


def test_do_not_contact_halts():
    h = pre_action_halt(txn(do_not_contact=True))
    assert h["reason"] == "do_not_contact_flag"


def test_retry_cap_is_code_aware():
    assert retry_cap("bank_decline") == 2
    assert retry_cap("insufficient_funds") == 3
    assert pre_action_halt(txn(failure_code="bank_decline", retry_count=2))["reason"] == "max_retries_reached"
    assert pre_action_halt(txn(failure_code="insufficient_funds", retry_count=2)) is None


def test_max_nudges_halt_on_checkout_abandon():
    h = pre_action_halt(txn(failure_stage="checkout_abandon", failure_code="otp_timeout", retry_count=2))
    assert h["reason"] == "max_nudges_reached"


def test_no_retry_on_card_expired_is_overridden():
    g = enforce_action_compliance("retry", txn(failure_code="card_expired"))
    assert g["overridden"] and g["decision"] == "send_reminder"


def test_repeated_failure_escalates():
    g = enforce_action_compliance("retry", txn(failure_code="insufficient_funds", retry_count=2))
    assert g["decision"] == "escalate_human"


def test_overdue_invoice_forces_escalation():
    g = enforce_action_compliance("send_reminder", txn(failure_code="invoice_unpaid", days_overdue=60))
    assert g["decision"] == "escalate_human"


def test_high_value_invoice_forces_escalation():
    g = enforce_action_compliance(
        "apply_discount", txn(failure_code="invoice_unpaid", days_overdue=5, customer_segment="high_value")
    )
    assert g["decision"] == "escalate_human"


def test_compliant_decision_untouched():
    g = enforce_action_compliance("send_reminder", txn(failure_code="otp_timeout"))
    assert not g["overridden"] and g["decision"] == "send_reminder"
