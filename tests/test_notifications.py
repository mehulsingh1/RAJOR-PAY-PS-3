"""Outbox + templates + promise-to-pay."""

from datetime import datetime, timezone

from notifications.templates import render, TEMPLATES
from notifications.outbox import Outbox, channel_for
from notifications.ptp import record_ptp, check_ptp
from tests.conftest import txn


def test_every_failure_code_has_en_and_hinglish():
    for code, tpl in TEMPLATES.items():
        assert tpl["en"] and tpl["hinglish"] and tpl["subject"]


def test_render_fills_placeholders():
    m = render("invoice_unpaid", txn(failure_code="invoice_unpaid", amount=5000, days_overdue=30), "hinglish")
    assert "5,000" in m["body"] and "{" not in m["body"] and m["lang"] == "hinglish"


def test_channel_selection_by_stage():
    assert channel_for("send_reminder", txn(failure_stage="receivable_overdue")) == "email"
    assert channel_for("send_reminder", txn(failure_stage="checkout_abandon")) == "whatsapp"
    assert channel_for("request_mandate_renewal", txn()) == "email"


def test_outbox_writes_record(tmp_path):
    ob = Outbox(path=str(tmp_path / "n.csv"))
    rec = ob.send(txn(failure_code="card_expired", preferred_language="en"), "send_reminder")
    assert rec["simulated"] is True and rec["cost"] > 0
    assert ob.for_txn(rec["txn_id"]) == [rec]
    assert Outbox(path=str(tmp_path / "n.csv")).all()  # persisted


def test_promise_to_pay_window_tiers():
    early = record_ptp(txn(days_overdue=10))
    late = record_ptp(txn(days_overdue=80))
    assert early["ptp_window_days"] > late["ptp_window_days"]
    assert early["ptp_status"] == "pending"


def test_check_ptp_breach():
    past = "2020-01-01"
    assert check_ptp(past, paid=False) == "breached"
    assert check_ptp(past, paid=True) == "kept"
    future = datetime(2999, 1, 1, tzinfo=timezone.utc).date().isoformat()
    assert check_ptp(future, paid=False) == "pending"
