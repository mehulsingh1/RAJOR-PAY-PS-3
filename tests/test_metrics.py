"""Metrics: metrics/engine.py"""

from metrics.engine import compute_metrics, compare_strategies
from tests.conftest import txn


def _result(amount, recovered, success, decision="retry", stop_reason=None,
            overridden=False, cost=0.0):
    return {
        "txn": txn(amount=amount),
        "decision": decision,
        "decision_overridden": overridden,
        "stop_reason": stop_reason,
        "action_result": {
            "success": success, "amount_recovered": recovered, "intervention_cost": cost,
        },
    }


def test_recovery_rate_and_totals():
    m = compute_metrics([
        _result(1000, 1000, True),
        _result(1000, 0, False),
    ])
    assert m["total_at_risk_amount"] == 2000
    assert m["total_recovered_amount"] == 1000
    assert m["recovery_rate_pct"] == 50.0


def test_halted_txns_count_as_at_risk_but_not_decisions():
    m = compute_metrics([
        _result(500, 0, False, stop_reason="do_not_contact_flag"),
        _result(1000, 1000, True),
    ])
    assert m["total_at_risk_amount"] == 1500
    assert m["stopped_count"] == 1
    assert m["stopped_by_reason"]["do_not_contact_flag"] == 1
    assert sum(m["decisions_breakdown"].values()) == 1


def test_compliance_overrides_counted():
    m = compute_metrics([_result(100, 100, True, overridden=True), _result(100, 0, False)])
    assert m["compliance_overrides_count"] == 1


def test_net_recovered_subtracts_cost():
    m = compute_metrics([_result(1000, 1000, True, cost=120.0)])
    assert m["total_intervention_cost"] == 120.0
    assert m["net_recovered_amount"] == 880.0


def test_compare_strategies_uplift_is_net_based():
    # agent recovers less gross but nets more (baseline burned cost on retries)
    agent = [_result(1000, 900, True, cost=10)]
    baselines = {"retry_all": [_result(1000, 1000, True, cost=300)]}
    cmp = compare_strategies(agent, baselines)
    up = cmp["agent_uplift_over_best_baseline"]
    assert up["vs"] == "retry_all"
    assert up["extra_gross_recovered"] == -100
    assert up["extra_net_recovered"] == 190  # 890 vs 700
