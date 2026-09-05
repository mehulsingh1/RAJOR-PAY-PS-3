"""Shared fixtures / sample transactions for the test suite."""

import pytest


def txn(**overrides):
    base = {
        "txn_id": "txn_test",
        "user_id": "user_test",
        "amount": 1000.0,
        "payment_method": "card",
        "failure_code": "insufficient_funds",
        "failure_stage": "payment_failure",
        "retry_count": 0,
        "do_not_contact": False,
        "customer_segment": "regular",
        "days_overdue": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def make_txn():
    return txn
