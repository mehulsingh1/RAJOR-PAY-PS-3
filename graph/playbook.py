"""
The knowledge-base playbook: the single best action per failure code, distilled
from rag/knowledge_base.json.

Used two ways:
  - the `static_playbook` baseline (baseline/strategy.py)
  - AGENT_MODE=playbook, which runs the agent's compliance + routing + costing
    pipeline but skips the LLM (fast, offline, deterministic — handy when the
    Groq quota is spent or for a reproducible demo)
"""

STATIC_PLAYBOOK = {
    "insufficient_funds": "send_reminder",
    "bank_decline": "escalate_human",
    "card_expired": "send_reminder",
    "issuer_timeout": "retry",
    "gateway_timeout": "retry",
    "otp_timeout": "send_reminder",
    "user_dropped": "apply_discount",
    "mandate_lapsed": "request_mandate_renewal",
    "invoice_unpaid": "escalate_human",
}

_ONE_LINER = {
    "insufficient_funds": "Balance was short at debit time; nudge the customer to top up, then retry.",
    "bank_decline": "The issuing bank blocked it; a human should switch method or call.",
    "card_expired": "Saved card is past expiry; ask the customer to update card details.",
    "issuer_timeout": "Transient issuer/infra timeout; a retry in the window usually clears it.",
    "gateway_timeout": "Gateway didn't respond during checkout; retry the checkout.",
    "otp_timeout": "Customer missed the OTP window; send a resume-checkout nudge.",
    "user_dropped": "Customer left checkout, likely price hesitation; a small incentive converts.",
    "mandate_lapsed": "E-mandate expired; a fresh re-authorization link is required (no silent retry).",
    "invoice_unpaid": "B2B invoice past due; escalate to collections with promise-to-pay tracking.",
}


def playbook_action(failure_code: str) -> str:
    return STATIC_PLAYBOOK.get(failure_code, "escalate_human")


def playbook_diagnosis(failure_code: str) -> str:
    return _ONE_LINER.get(failure_code, f"Failure '{failure_code}' — see knowledge base.")
