"""
Non-AI baseline strategies, for measuring how much the reasoning agent actually adds.

Every baseline runs against the SAME outcome model (mcp_tools.tools) and the SAME
compliance halts (graph.compliance) as the agent — the only thing that differs is
how the intervention is chosen. So the agent-vs-baseline delta isolates the value
of the diagnosis + decision step, not of the plumbing around it.

Results are shaped like the agent's final LangGraph state, so metrics.engine
computes them with no special-casing.
"""

import copy

from graph.compliance import pre_action_halt, retry_cap
from graph.playbook import STATIC_PLAYBOOK
from mcp_tools.tools import execute_action

BASELINE_POLICIES = ["retry_all", "reminder_all", "static_playbook"]

_LABELS = {
    "retry_all": "Retry everything",
    "reminder_all": "Always send a reminder",
    "static_playbook": "Static KB playbook (no AI)",
}


def policy_label(policy: str) -> str:
    return _LABELS.get(policy, policy)


def _pick(policy: str, txn: dict) -> str:
    if policy == "retry_all":
        return "retry"
    if policy == "reminder_all":
        return "send_reminder"
    if policy == "static_playbook":
        return STATIC_PLAYBOOK.get(txn.get("failure_code", ""), "escalate_human")
    raise ValueError(f"unknown baseline policy: {policy}")


def _run_one(policy: str, txn: dict) -> dict:
    txn = copy.deepcopy(txn)
    decision = _pick(policy, txn)
    result = {}
    attempts = []

    # Same bounded follow-up rules the agent uses (graph/nodes.route_after_act):
    # retry loops to the compliance cap; a nudge/renewal gets one follow-up.
    while True:
        halt = pre_action_halt(txn)
        if halt:
            return {
                "txn": txn,
                "stop_reason": halt["reason"],
                "decision": decision,
                "decision_reasoning": f"baseline:{policy}",
                "decision_overridden": False,
                "action_result": result,
                "attempts": attempts,
            }

        result = execute_action(decision, txn)
        attempts.append(result)
        done = txn.get("retry_count", 0)

        if result.get("success"):
            break
        if decision == "retry" and done < retry_cap(txn.get("failure_code", "")):
            txn["retry_count"] = done + 1
            continue
        if decision in {"send_reminder", "apply_discount", "request_mandate_renewal"} and done < 1:
            txn["retry_count"] = done + 1
            continue
        break

    return {
        "txn": txn,
        "stop_reason": None,
        "decision": decision,
        "decision_reasoning": f"baseline:{policy}",
        "decision_overridden": False,
        "action_result": result,
        "attempts": attempts,
    }


def run_baseline(rows: list[dict], policy: str) -> list[dict]:
    """Run one baseline policy over a batch. Returns agent-shaped result states."""
    return [_run_one(policy, txn) for txn in rows]


def run_all_baselines(rows: list[dict]) -> dict:
    """{policy: [result states]} for every baseline policy."""
    return {p: run_baseline(rows, p) for p in BASELINE_POLICIES}
