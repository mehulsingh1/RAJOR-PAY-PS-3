"""
Compliance / business-rule engine for the recovery workflow.

Turns the prose `compliance_notes` in rag/knowledge_base.json into rules that
actually bind:

  pre_action_halt        - hard stops evaluated BEFORE any intervention
  enforce_action_compliance - guardrails that override a non-compliant decision

Every decision here is returned with a human-readable note so the audit trail
shows exactly which rule fired and why.
"""

from typing import Optional

# RBI auto-debit mandate: max 3 retries. Card declines are tighter.
DEFAULT_RETRY_CAP = 3
RETRY_CAP = {
    "bank_decline": 2,   # KB: no more than 2 retries without re-authorization
}

# Codes where an auto-retry is never allowed (expired card, lapsed mandate,
# or checkout abandons where no debit ever occurred).
NO_AUTO_RETRY = {
    "card_expired": "send_reminder",
    "mandate_lapsed": "request_mandate_renewal",
    "otp_timeout": "send_reminder",
    "gateway_timeout": "send_reminder",
    "user_dropped": "send_reminder",
}

# Comms-only stages: max nudges before we stop pestering the customer.
MAX_NUDGES = 2
COMMS_ONLY_STAGES = {"checkout_abandon"}

# Invoice collections: escalate to a human past this age.
INVOICE_ESCALATE_DAYS = 45


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def retry_cap(failure_code: str) -> int:
    return RETRY_CAP.get(failure_code, DEFAULT_RETRY_CAP)


def pre_action_halt(txn: dict) -> Optional[dict]:
    """Hard stop before acting. Returns {reason, detail} or None to proceed."""
    code = txn.get("failure_code", "")
    stage = txn.get("failure_stage", "")
    rc = int(txn.get("retry_count", 0) or 0)

    if txn.get("do_not_contact"):
        return {
            "reason": "do_not_contact_flag",
            "detail": "Customer opted out of contact — all recovery outreach suppressed.",
        }

    cap = retry_cap(code)
    if rc >= cap:
        return {
            "reason": "max_retries_reached",
            "detail": f"retry_count={rc} has hit the cap of {cap} for '{code}' "
                      f"(RBI auto-debit mandate limit).",
        }

    if stage in COMMS_ONLY_STAGES and rc >= MAX_NUDGES:
        return {
            "reason": "max_nudges_reached",
            "detail": f"{rc} recovery nudges already sent for a {stage} — KB caps at "
                      f"{MAX_NUDGES}. Stopping to avoid harassment.",
        }

    return None


def enforce_action_compliance(decision: str, txn: dict) -> dict:
    """
    Apply guardrails to a chosen decision. May override it.
    Returns {decision, original_decision, overridden, notes}.
    """
    code = txn.get("failure_code", "")
    rc = int(txn.get("retry_count", 0) or 0)
    notes: list[str] = []
    final = decision

    # 1. No auto-retry on codes the KB forbids it for.
    if final == "retry" and code in NO_AUTO_RETRY:
        alt = NO_AUTO_RETRY[code]
        notes.append(
            f"Blocked 'retry' on '{code}' — KB: no auto-retry permitted; "
            f"substituted '{alt}'."
        )
        final = alt

    # 2. Repeated failures -> escalate to a human rather than retry again.
    if final == "retry" and rc >= 2:
        notes.append(
            f"'retry' after {rc} failed attempts — escalating to a human "
            f"(repeated-failure policy)."
        )
        final = "escalate_human"

    # 3. Overdue / high-value invoices must go to collections.
    if code == "invoice_unpaid":
        days = _to_float(txn.get("days_overdue"))
        high_value = txn.get("customer_segment") == "high_value"
        if ((days is not None and days > INVOICE_ESCALATE_DAYS) or high_value) and final != "escalate_human":
            trigger = "high-value account" if high_value else f"{days:.0f}d overdue"
            notes.append(
                f"Invoice ({trigger}) exceeds collections threshold — forcing "
                f"'escalate_human' (was '{final}')."
            )
            final = "escalate_human"

    # 4. Informational: retry spacing (synthetic timestamps, so not enforced here).
    if final == "retry" and rc >= 1:
        notes.append(
            "24h minimum retry spacing assumed satisfied (synthetic timestamps); "
            "in production this would gate on last_attempt_at."
        )

    return {
        "decision": final,
        "original_decision": decision,
        "overridden": final != decision,
        "notes": notes,
    }
