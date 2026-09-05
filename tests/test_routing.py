"""Second-touch routing: graph/nodes.route_after_act"""

from graph.nodes import route_after_act
from tests.conftest import txn


def _state(decision, success, retry_count=0, code="insufficient_funds"):
    return {
        "txn": txn(failure_code=code, retry_count=retry_count),
        "decision": decision,
        "action_result": {"success": success},
    }


def test_success_goes_to_log():
    assert route_after_act(_state("send_reminder", True)) == "log"


def test_failed_reminder_gets_one_follow_up_then_stops():
    s = _state("send_reminder", False, retry_count=0)
    assert route_after_act(s) == "stop_check"
    assert s["txn"]["retry_count"] == 1
    s2 = _state("send_reminder", False, retry_count=1)
    assert route_after_act(s2) == "log"


def test_failed_retry_loops_to_compliance_cap():
    s = _state("retry", False, retry_count=0, code="insufficient_funds")  # cap 3
    assert route_after_act(s) == "stop_check"
    s2 = _state("retry", False, retry_count=2, code="insufficient_funds")
    assert route_after_act(s2) == "stop_check"  # 3rd attempt allowed
    s3 = _state("retry", False, retry_count=3, code="insufficient_funds")
    assert route_after_act(s3) == "log"


def test_failed_escalation_is_terminal():
    assert route_after_act(_state("escalate_human", False)) == "log"
