"""
Recovery-action tools for the Act node (also exposed over MCP in mcp_server/).

The outcome is NOT a blind coin flip — success probability is a function of:
  - the failure_code (why the payment failed)
  - the action the agent chose (is it the right fix for that failure?)
  - transaction features (retry_count, days_overdue, customer_segment, method)

so a well-reasoned decision genuinely recovers more money than a naive one.
Each attempt also carries an intervention cost (mcp_tools/costs.py) so the
headline metric can be NET recovered.

Outcomes are deterministic for a given (seed, txn_id, action, attempt), so runs
are reproducible and independent of queue order.
"""

import os
import random

from mcp_tools.costs import intervention_cost, channel_for
from learning.priors import PRIORS

# Global seed — override with env RECOVERY_SEED for a different reproducible run.
SEED = os.getenv("RECOVERY_SEED", "42")

ALL_ACTIONS = [
    "retry",
    "send_reminder",
    "apply_discount",
    "escalate_human",
    "request_mandate_renewal",
]

# Base P(success) for (failure_code, immediate action). Calibrated to be
# realistic, NOT to flatter the agent:
#   - immediate `retry` only works when the root cause is transient
#     (issuer/gateway timeout). For "no money" / "bank blocked" / "expired" it is
#     near-useless, and the KB says so.
#   - each failure code has a clear best *non-brute* action.
# Rationale per row in the comment.
BASE_SUCCESS = {
    # balance low near month-end: money isn't there yet -> nudge to top up, then retry
    "insufficient_funds": {
        "retry": 0.18, "send_reminder": 0.46, "apply_discount": 0.22,
        "escalate_human": 0.30, "request_mandate_renewal": 0.05,
    },
    # issuer blocked it (risk/limit): same path re-declines -> switch method / human
    "bank_decline": {
        "retry": 0.24, "send_reminder": 0.44, "apply_discount": 0.18,
        "escalate_human": 0.50, "request_mandate_renewal": 0.05,
    },
    # card past expiry: retry ALWAYS fails (KB) -> ask customer to update card
    "card_expired": {
        "retry": 0.02, "send_reminder": 0.58, "apply_discount": 0.15,
        "escalate_human": 0.42, "request_mandate_renewal": 0.50,
    },
    # transient issuer infra: retrying genuinely works
    "issuer_timeout": {
        "retry": 0.74, "send_reminder": 0.28, "apply_discount": 0.12,
        "escalate_human": 0.32, "request_mandate_renewal": 0.05,
    },
    # transient gateway infra during checkout (no debit): retry or resume-link
    "gateway_timeout": {
        "retry": 0.66, "send_reminder": 0.60, "apply_discount": 0.22,
        "escalate_human": 0.25, "request_mandate_renewal": 0.05,
    },
    # customer didn't enter OTP (checkout abandon): nothing to retry -> resume nudge
    "otp_timeout": {
        "retry": 0.12, "send_reminder": 0.56, "apply_discount": 0.38,
        "escalate_human": 0.20, "request_mandate_renewal": 0.05,
    },
    # voluntary exit / price hesitation: an incentive converts best
    "user_dropped": {
        "retry": 0.06, "send_reminder": 0.40, "apply_discount": 0.54,
        "escalate_human": 0.16, "request_mandate_renewal": 0.05,
    },
    # e-mandate expired/revoked: no silent retry (RBI) -> renewal link
    "mandate_lapsed": {
        "retry": 0.02, "send_reminder": 0.28, "apply_discount": 0.12,
        "escalate_human": 0.40, "request_mandate_renewal": 0.70,
    },
    # B2B invoice overdue: reminder decays with age, collections escalation improves
    "invoice_unpaid": {
        "retry": 0.04, "send_reminder": 0.48, "apply_discount": 0.42,
        "escalate_human": 0.60, "request_mandate_renewal": 0.04,
    },
}

DEFAULT_BASE = 0.10

# Attempts allowed per action before the workflow must finalise.
# retry uses the compliance cap (graph/compliance.retry_cap); nudges cap at 2 (KB).
NUDGE_ACTIONS = {"send_reminder", "apply_discount"}
NUDGE_CAP = 2


def _rng(txn: dict, action: str) -> random.Random:
    """Deterministic per-(txn, action, attempt) RNG — order-independent."""
    attempt = int(txn.get("retry_count", 0) or 0)
    return random.Random(f"{SEED}:{txn.get('txn_id')}:{action}:{attempt}")


def _success_probability(action: str, txn: dict) -> float:
    """Feature-adjusted success probability for this action on this txn."""
    code = txn.get("failure_code", "")
    p = BASE_SUCCESS.get(code, {}).get(action, DEFAULT_BASE)

    # Attempt fatigue — steep: attempt 0->x1.0, 1->x0.70, 2->x0.40, 3->x0.15.
    attempt = int(txn.get("retry_count", 0) or 0)
    p *= max(0.15, 1.0 - 0.30 * attempt)

    # High-value customers: escalation and negotiation land better.
    if txn.get("customer_segment") == "high_value":
        if action == "escalate_human":
            p += 0.12
        elif action == "apply_discount":
            p += 0.06

    # Overdue B2B invoices: reminders decay with age, escalation improves.
    if code == "invoice_unpaid":
        try:
            d = float(txn.get("days_overdue"))
            if d == d:  # not NaN
                if action == "send_reminder":
                    p -= min(0.30, 0.004 * d)
                elif action == "escalate_human":
                    p += min(0.20, 0.003 * d)
        except (TypeError, ValueError):
            pass

    # UPI retries recover slightly better than netbanking for transient failures.
    if action == "retry" and code in ("issuer_timeout", "gateway_timeout"):
        if txn.get("payment_method") == "upi":
            p += 0.05

    p = max(0.02, min(0.97, p))
    # Online learning: nudge toward the rate we've actually observed this run.
    return PRIORS.blend(p, code, action)


def _simulate_outcome(action: str, txn: dict) -> dict:
    """Shared probabilistic outcome logic, feature- and decision-aware."""
    amount = float(txn.get("amount", 0.0) or 0.0)
    p = _success_probability(action, txn)
    success = _rng(txn, action).random() < p
    channel = channel_for(action, txn)

    return {
        "action": action,
        "channel": channel,
        "success": success,
        "amount_recovered": round(amount, 2) if success else 0.0,
        "success_probability": round(p, 3),
        "intervention_cost": intervention_cost(action, txn, success, channel),
    }


def _with_message(result: dict, txn: dict, ok_msg: str, fail_msg: str) -> dict:
    result["message"] = (
        f"{ok_msg if result['success'] else fail_msg} (txn {txn['txn_id']})."
    )
    return result


def retry_payment(txn: dict) -> dict:
    r = _simulate_outcome("retry", txn)
    return _with_message(
        r, txn,
        f"Retry on {txn.get('payment_method', 'source')} succeeded",
        f"Retry on {txn.get('payment_method', 'source')} failed again",
    )


def send_reminder(txn: dict) -> dict:
    r = _simulate_outcome("send_reminder", txn)
    return _with_message(
        r, txn, "Reminder sent — customer completed payment", "Reminder sent — no response yet",
    )


def apply_discount(txn: dict) -> dict:
    r = _simulate_outcome("apply_discount", txn)
    return _with_message(
        r, txn, "Discount offer accepted — customer paid", "Discount offer not taken up",
    )


def escalate_human(txn: dict) -> dict:
    r = _simulate_outcome("escalate_human", txn)
    return _with_message(
        r, txn, "Escalated to collections — resolved by agent", "Escalated to collections — pending follow-up",
    )


def request_mandate_renewal(txn: dict) -> dict:
    r = _simulate_outcome("request_mandate_renewal", txn)
    return _with_message(
        r, txn, "Mandate renewal link sent — customer re-authorized", "Mandate renewal link sent — no re-authorization yet",
    )


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
            "channel": "none",
            "success": False,
            "amount_recovered": 0.0,
            "success_probability": 0.0,
            "intervention_cost": 0.0,
            "message": f"Unknown action '{decision}' — no tool mapped.",
        }
    return tool_fn(txn)
