"""
Aggregates raw LangGraph batch results into judge-facing metrics.
"""

from collections import defaultdict


def _attempt_costs(r: dict) -> list[float]:
    """Per-attempt intervention costs for one result state (agent or baseline)."""
    if r.get("attempts"):  # baseline result states carry an explicit list
        return [float(a.get("intervention_cost", 0) or 0) for a in r["attempts"]]
    log = r.get("audit_log")  # agent: one entry per attempt (skip summary/halt rows)
    if log:
        return [
            float(e["action_result"].get("intervention_cost", 0) or 0)
            for e in log
            if "entry_type" not in e and isinstance(e.get("action_result"), dict)
        ]
    ar = r.get("action_result") or {}
    return [float(ar.get("intervention_cost", 0) or 0)] if ar else []


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
    compliance_overrides_count = 0
    total_cost = 0.0

    for r in results:
        txn = r["txn"]
        amount = float(txn["amount"])
        stage = txn.get("failure_stage", "unknown")

        total_at_risk += amount
        at_risk_by_stage[stage] += amount
        total_cost += sum(_attempt_costs(r))  # counted even if the txn later halted

        if r.get("decision_overridden"):
            compliance_overrides_count += 1

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

    net_recovered = total_recovered - total_cost
    recovery_rate_pct = (
        round((total_recovered / total_at_risk) * 100, 2) if total_at_risk > 0 else 0.0
    )
    net_recovery_rate_pct = (
        round((net_recovered / total_at_risk) * 100, 2) if total_at_risk > 0 else 0.0
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
        "total_intervention_cost": round(total_cost, 2),
        "net_recovered_amount": round(net_recovered, 2),
        "recovery_rate_pct": recovery_rate_pct,
        "net_recovery_rate_pct": net_recovery_rate_pct,
        "stopped_count": stopped_count,
        "stopped_by_reason": dict(stopped_by_reason),
        "compliance_overrides_count": compliance_overrides_count,
        "decisions_breakdown": dict(decisions_breakdown),
        "success_rate_by_decision_pct": success_rate_by_decision,
        "escalations_count": escalations_count,
        "at_risk_by_stage": {k: round(v, 2) for k, v in at_risk_by_stage.items()},
        "recovered_by_stage": {k: round(v, 2) for k, v in recovered_by_stage.items()},
    }


def compare_strategies(agent_results: list, baseline_results: dict) -> dict:
    """
    agent_results: list of final agent states.
    baseline_results: {policy_name: list of baseline result states}.
    Returns a side-by-side comparison plus the agent's uplift over the best baseline.
    """
    def _row(m):
        return {
            "recovered": m["total_recovered_amount"],
            "intervention_cost": m["total_intervention_cost"],
            "net_recovered": m["net_recovered_amount"],
            "recovery_rate_pct": m["recovery_rate_pct"],
            "net_recovery_rate_pct": m["net_recovery_rate_pct"],
        }

    agent_m = compute_metrics(agent_results)
    rows = {"agent": _row(agent_m)}
    for name, results in baseline_results.items():
        rows[name] = _row(compute_metrics(results))

    # The fair competitor is the baseline that nets the most money.
    best_baseline = max(
        (n for n in rows if n != "agent"),
        key=lambda n: rows[n]["net_recovered"],
        default=None,
    )
    uplift = None
    if best_baseline is not None:
        b = rows[best_baseline]
        a = rows["agent"]
        uplift = {
            "vs": best_baseline,
            "extra_net_recovered": round(a["net_recovered"] - b["net_recovered"], 2),
            "extra_gross_recovered": round(a["recovered"] - b["recovered"], 2),
            "extra_net_rate_pp": round(
                a["net_recovery_rate_pct"] - b["net_recovery_rate_pct"], 2
            ),
        }

    return {
        "total_at_risk_amount": agent_m["total_at_risk_amount"],
        "by_strategy": rows,
        "agent_uplift_over_best_baseline": uplift,
    }
