"""
MCP-style tool functions for the Act node.
Each simulates a real Razorpay-side recovery action with a realistic
success probability and partial/full recovery amount — not always 100%.

Structured as plain callable functions now (clean interface for the graph).
Can be wrapped as an actual MCP server later without changing this logic.
"""

import random

# Success probability per action — based on real-world recovery patterns
SUCCESS_RATES = {
    "retry": 0.55,
    "send_reminder": 0.35,
    "apply_discount": 0.45,
    "escalate_human": 0.70,
    "request_mandate_renewal": 0.30,
}


def _simulate_outcome(action: str, amount: float) -> dict:
    """Shared probabilistic outcome logic."""
    success = random.random() < SUCCESS_RATES[action]
    amount_recovered = round(amount, 2) if success else 0.0
    return {
        "action": action,
        "success": success,
        "amount_recovered": amount_recovered,
    }


def retry_payment(txn: dict) -> dict:
    result = _simulate_outcome("retry", txn["amount"])
    result["message"] = (
        f"Retry attempted on {txn['payment_method']} for txn {txn['txn_id']}. "
        f"{'Succeeded' if result['success'] else 'Failed again'}."
    )
    return result


def send_reminder(txn: dict) -> dict:
    result = _simulate_outcome("send_reminder", txn["amount"])
    result["message"] = (
        f"Reminder sent to customer for txn {txn['txn_id']}. "
        f"{'Customer completed payment' if result['success'] else 'No response yet'}."
    )
    return result


def apply_discount(txn: dict) -> dict:
    result = _simulate_outcome("apply_discount", txn["amount"])
    if result["success"]:
        # simulate a small discount reducing recovered amount slightly
        result["amount_recovered"] = round(txn["amount"] * 0.92, 2)
    result["message"] = (
        f"Discount offer sent for txn {txn['txn_id']}. "
        f"{'Customer accepted and paid' if result['success'] else 'Offer not taken up'}."
    )
    return result


def escalate_human(txn: dict) -> dict:
    result = _simulate_outcome("escalate_human", txn["amount"])
    result["message"] = (
        f"Escalated txn {txn['txn_id']} to human collections agent. "
        f"{'Resolved by agent' if result['success'] else 'Still pending agent follow-up'}."
    )
    return result


def request_mandate_renewal(txn: dict) -> dict:
    result = _simulate_outcome("request_mandate_renewal", txn["amount"])
    result["message"] = (
        f"Mandate renewal link sent for txn {txn['txn_id']}. "
        f"{'Customer re-authorized mandate' if result['success'] else 'No re-authorization yet'}."
    )
    return result


# Dispatch table used by the Act node
TOOL_DISPATCH = {
    "retry": retry_payment,
    "send_reminder": send_reminder,
    "apply_discount": apply_discount,
    "escalate_human": escalate_human,
    "request_mandate_renewal": request_mandate_renewal,
}


def execute_action(decision: str, txn: dict) -> dict:
    """Single entry point the Act node calls."""
    tool_fn = TOOL_DISPATCH.get(decision)
    if tool_fn is None:
        return {
            "action": decision,
            "success": False,
            "amount_recovered": 0.0,
            "message": f"Unknown action '{decision}' — no tool mapped.",
        }
    return tool_fn(txn)
