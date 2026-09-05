"""Baseline strategies: baseline/strategy.py"""

from baseline.strategy import run_baseline, run_all_baselines, BASELINE_POLICIES
from tests.conftest import txn


def test_result_shape_matches_agent_state():
    r = run_baseline([txn()], "retry_all")[0]
    assert {"txn", "stop_reason", "decision", "action_result"} <= set(r)


def test_respects_do_not_contact_halt():
    r = run_baseline([txn(do_not_contact=True)], "reminder_all")[0]
    assert r["stop_reason"] == "do_not_contact_flag"


def test_retry_loop_is_bounded():
    # card_expired retry always fails; must terminate, not loop forever
    r = run_baseline([txn(failure_code="card_expired")], "retry_all")[0]
    assert r["txn"]["retry_count"] <= 3


def test_static_playbook_routes_by_code():
    r = run_baseline([txn(failure_code="mandate_lapsed")], "static_playbook")[0]
    assert r["decision"] == "request_mandate_renewal"


def test_run_all_baselines_covers_every_policy():
    out = run_all_baselines([txn()])
    assert set(out) == set(BASELINE_POLICIES)
