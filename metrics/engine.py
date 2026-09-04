"""
Aggregates raw LangGraph batch results into judge-facing metrics.
"""

from collections import defaultdict


def compute_metrics(results: list) -> dict:
    """
    results: list of final LangGraph states, one per processed transaction.
    Returns a dict of aggregate metrics.
    """
    total_transactions = len(results)
    total_at_risk = 0.0
    total_recovered = 0.0

    stopped_count = 0
    stopped_by_reason = defaultdict(int)

    decisions_breakdown = defaultdict(int)
    decision_attempts = defaultdict(int)
    decision_successes = defaultdict(int)

    recovered_by_stage = defaultdict(float)
    at_risk_by_stage = defaultdict(float)

    escalations_count = 0

    for r in results:
        txn = r["txn"]
        amount = float(txn["amount"])
        stage = txn.get("failure_stage", "unknown")

        total_at_risk += amount
        at_risk_by_stage[stage] += amount

        stop_reason = r.get("stop_reason")
        if stop_reason:
            stopped_count += 1
            stopped_by_reason[stop_reason] += 1
            continue  # no decision/action was taken for halted txns

        decision = r.get("decision", "none")
        decisions_breakdown[decision] += 1
        decision_attempts[decision] += 1

        if decision == "escalate_human":
            escalations_count += 1

        action_result = r.get("action_result", {})
        recovered = float(action_result.get("amount_recovered", 0.0))
        total_recovered += recovered
        recovered_by_stage[stage] += recovered

        if action_result.get("success"):
            decision_successes[decision] += 1

    recovery_rate_pct = (
        round((total_recovered / total_at_risk) * 100, 2) if total_at_risk > 0 else 0.0
    )

    success_rate_by_decision = {
        decision: round((decision_successes[decision] / attempts) * 100, 1)
        for decision, attempts in decision_attempts.items()
        if attempts > 0
    }

    return {
        "total_transactions": total_transactions,
        "total_at_risk_amount": round(total_at_risk, 2),
        "total_recovered_amount": round(total_recovered, 2),
        "recovery_rate_pct": recovery_rate_pct,
        "stopped_count": stopped_count,
        "stopped_by_reason": dict(stopped_by_reason),
        "decisions_breakdown": dict(decisions_breakdown),
        "success_rate_by_decision_pct": success_rate_by_decision,
        "escalations_count": escalations_count,
        "at_risk_by_stage": {k: round(v, 2) for k, v in at_risk_by_stage.items()},
        "recovered_by_stage": {k: round(v, 2) for k, v in recovered_by_stage.items()},
    }
