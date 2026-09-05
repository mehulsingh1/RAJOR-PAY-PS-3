"""
Detection / prioritization logic for the Detect stage.

`score_transaction` turns a raw transaction row into a revenue-at-risk assessment:
how much money is realistically recoverable, how urgent it is, and why it was
flagged. The batch runners use it to work the highest-value recoverable revenue
first instead of processing in arbitrary CSV order.
"""

from mcp_tools.tools import ALL_ACTIONS, _success_probability

# Rough urgency per failure_code, distilled from rag/knowledge_base.json.
SEVERITY = {
    "card_expired": 0.90,
    "mandate_lapsed": 0.90,
    "invoice_unpaid": 0.80,
    "otp_timeout": 0.70,
    "gateway_timeout": 0.60,
    "bank_decline": 0.50,
    "insufficient_funds": 0.50,
    "issuer_timeout": 0.40,
    "user_dropped": 0.30,
}

# Amount that counts as "large" for value-normalisation.
VALUE_CAP = 5000.0

WEIGHTS = {
    "value": 0.35,          # how much money is on the line
    "recoverability": 0.30,  # can we realistically get it back
    "urgency": 0.20,         # how time-sensitive the failure is
    "overdue": 0.10,         # age of an overdue receivable
    "segment": 0.05,         # high-value customer relationship
}


def _best_recovery_probability(txn: dict) -> tuple[float, str]:
    """Best achievable success probability across all actions, and which action."""
    scored = [(a, _success_probability(a, txn)) for a in ALL_ACTIONS]
    best_action, best_p = max(scored, key=lambda x: x[1])
    return best_p, best_action


def _overdue_component(txn: dict) -> float:
    if txn.get("failure_code") != "invoice_unpaid":
        return 0.0
    d = txn.get("days_overdue")
    try:
        return max(0.0, min(1.0, float(d) / 90.0))
    except (TypeError, ValueError):
        return 0.0


def score_transaction(txn: dict) -> dict:
    """Return a detection assessment for one transaction."""
    amount = float(txn.get("amount", 0.0) or 0.0)
    code = txn.get("failure_code", "unknown")

    best_p, best_action = _best_recovery_probability(txn)

    components = {
        "value": min(amount / VALUE_CAP, 1.0),
        "recoverability": best_p,
        "urgency": SEVERITY.get(code, 0.4),
        "overdue": _overdue_component(txn),
        "segment": 1.0 if txn.get("customer_segment") == "high_value" else 0.0,
    }
    risk_score = round(100.0 * sum(WEIGHTS[k] * v for k, v in components.items()), 1)

    if risk_score >= 60:
        tier = "high"
    elif risk_score >= 35:
        tier = "medium"
    else:
        tier = "low"

    expected_recoverable = round(amount * best_p, 2)

    # Human-readable "why flagged" — top 2 contributing drivers.
    contributions = {k: WEIGHTS[k] * components[k] for k in components}
    top = sorted(contributions, key=contributions.get, reverse=True)[:2]
    driver_labels = {
        "value": f"Rs {amount:,.0f} at stake",
        "recoverability": f"{best_p:.0%} recoverable via {best_action}",
        "urgency": f"{code} is time-sensitive",
        "overdue": f"{txn.get('days_overdue')}d overdue",
        "segment": "high-value customer",
    }
    reason = "; ".join(driver_labels[k] for k in top)
    if txn.get("do_not_contact"):
        reason += "; outreach restricted (do_not_contact)"

    return {
        "risk_score": risk_score,
        "risk_tier": tier,
        "risk_reason": reason,
        "expected_recoverable": expected_recoverable,
        "suggested_action": best_action,
    }


def prioritized(rows: list[dict]) -> list[dict]:
    """Sort a batch so the highest-value recoverable revenue is worked first."""
    return sorted(
        rows,
        key=lambda t: score_transaction(t)["expected_recoverable"],
        reverse=True,
    )
