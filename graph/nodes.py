"""
LangGraph node functions: Detect / StopCheck / Diagnose / Decide / Act / Log.
Diagnose + Decide use real RAG retrieval + Groq LLM reasoning.
"""

import json
import os
import sys
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import RecoveryState
from graph.detection import score_transaction
from graph.compliance import pre_action_halt, enforce_action_compliance, retry_cap
from llm.client import invoke_text
from mcp_tools.tools import execute_action
from notifications.outbox import Outbox
from notifications.ptp import record_ptp
from learning.priors import PRIORS
from graph.playbook import playbook_action, playbook_diagnosis


def _playbook_mode() -> bool:
    """AGENT_MODE=playbook skips the LLM in Diagnose/Decide (fast, offline,
    deterministic); default 'llm' drives them with Groq. Read per call so the
    live backend can flip it without a reload."""
    return os.getenv("AGENT_MODE", "llm").lower() == "playbook"

# Actions that put a message in the customer's inbox.
MESSAGING_ACTIONS = {"send_reminder", "apply_discount", "request_mandate_renewal"}

_outbox = Outbox()


def set_outbox(outbox: Outbox) -> None:
    """Let the live backend (Step C) swap in its own outbox / CSV path."""
    global _outbox
    _outbox = outbox


def _log(msg: str) -> None:
    """print() that never crashes on LLM text the console encoding can't handle
    (e.g. a non-breaking hyphen U+2011 on a cp1252 Windows terminal)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc))

# Route Act through the real MCP server when USE_MCP is set; otherwise call the
# tool functions directly (faster for large batches, no subprocess).
USE_MCP = os.getenv("USE_MCP", "").lower() in ("1", "true", "yes")


def _run_action(decision: str, txn: dict) -> dict:
    if not USE_MCP:
        return execute_action(decision, txn)
    try:
        from mcp_tools.client import get_client
        return get_client().call(decision, txn)
    except Exception as e:  # server missing / crashed -> don't lose the batch
        _log(f"[Act] MCP call failed ({e}); falling back to direct execution")
        return execute_action(decision, txn)

ALLOWED_DECISIONS = [
    "retry",
    "send_reminder",
    "apply_discount",
    "escalate_human",
    "request_mandate_renewal",
]


def detect_node(state: RecoveryState) -> RecoveryState:
    """Assess revenue at risk: recovery priority, expected recoverable ₹, and why."""
    txn = state["txn"]
    assessment = score_transaction(txn)

    state["risk_score"] = assessment["risk_score"]
    state["risk_tier"] = assessment["risk_tier"]
    state["risk_reason"] = assessment["risk_reason"]
    state["expected_recoverable"] = assessment["expected_recoverable"]

    _log(
        f"[Detect] {txn['txn_id']} - risk={assessment['risk_score']} "
        f"({assessment['risk_tier']}) - expected recoverable Rs {assessment['expected_recoverable']:,.0f} "
        f"- {assessment['risk_reason']}"
    )
    return state


def stop_check_node(state: RecoveryState) -> RecoveryState:
    """Apply compliance / business stopping rules before acting (see graph/compliance.py)."""
    txn = state["txn"]
    halt = pre_action_halt(txn)

    if halt:
        state["stop_reason"] = halt["reason"]
        note = f"HALT [{halt['reason']}] — {halt['detail']}"
        state["compliance_notes"] = state.get("compliance_notes", []) + [note]
        state["audit_log"] = state.get("audit_log", []) + [{
            "txn_id": txn["txn_id"],
            "entry_type": "compliance_halt",
            "reason": halt["reason"],
            "detail": halt["detail"],
            "retry_count_at_halt": txn.get("retry_count", 0),
            "timestamp": datetime.now().isoformat(),
        }]
        _log(f"[StopCheck] {note}")
    else:
        state["stop_reason"] = None
        _log("[StopCheck] Clear to proceed")
    return state


def diagnose_node(state: RecoveryState) -> RecoveryState:
    """Retrieve KB context and ask LLM to reason about root cause."""
    txn = state["txn"]

    if _playbook_mode():
        state["rag_context"] = ""
        state["diagnosis"] = playbook_diagnosis(txn["failure_code"])
        _log(f"[Diagnose] {state['diagnosis']}")
        return state

    from rag.retriever import retrieve_context  # lazy: keeps chromadb off the import path

    rag_context = retrieve_context(txn["failure_code"], k=1)
    state["rag_context"] = rag_context

    system_msg = SystemMessage(
        content=(
            "You are a revenue recovery diagnosis agent for a payments company. "
            "Given a failed transaction and knowledge base context, state the most "
            "likely root cause in 1-2 concise sentences. Be specific, not generic."
        )
    )
    human_msg = HumanMessage(
        content=(
            f"Transaction:\n"
            f"- failure_code: {txn['failure_code']}\n"
            f"- stage: {txn['failure_stage']}\n"
            f"- amount: {txn['amount']}\n"
            f"- payment_method: {txn['payment_method']}\n"
            f"- retry_count: {txn.get('retry_count', 0)}\n\n"
            f"Knowledge base context:\n{rag_context}\n\n"
            f"What is the root cause here?"
        )
    )

    fallback = (
        f"[fallback diagnosis] LLM unavailable. Based on the knowledge base, the "
        f"likely root cause for '{txn['failure_code']}' is described above."
    )
    state["diagnosis"] = invoke_text([system_msg, human_msg], fallback=fallback)
    _log(f"[Diagnose] {state['diagnosis']}")
    return state


def decide_node(state: RecoveryState) -> RecoveryState:
    """Pick ONE intervention. LLM mode asks Groq for structured JSON; playbook mode
    uses the KB action. Both then pass through the compliance guardrails."""
    txn = state["txn"]

    if _playbook_mode():
        decision = playbook_action(txn["failure_code"])
        reasoning = f"KB playbook: {playbook_diagnosis(txn['failure_code'])}"
        return _apply_decision(state, txn, decision, reasoning)

    system_msg = SystemMessage(
        content=(
            "You are a revenue recovery decision agent. Based on the diagnosis and "
            "transaction details, choose exactly ONE intervention from this fixed list:\n"
            f"{ALLOWED_DECISIONS}\n\n"
            "Respond with ONLY valid JSON, no markdown fences, no extra text:\n"
            '{"decision": "<one_of_allowed>", "reasoning": "<1 sentence>"}'
        )
    )
    human_msg = HumanMessage(
        content=(
            f"Diagnosis: {state['diagnosis']}\n\n"
            f"Transaction:\n"
            f"- failure_code: {txn['failure_code']}\n"
            f"- stage: {txn['failure_stage']}\n"
            f"- amount: {txn['amount']}\n"
            f"- customer_segment: {txn.get('customer_segment', 'regular')}\n"
            f"- retry_count: {txn.get('retry_count', 0)}\n"
            f"- days_overdue: {txn.get('days_overdue')}\n\n"
            f"Knowledge base compliance context:\n{state['rag_context']}"
        )
    )

    # On total LLM failure, fall back to a valid JSON that routes to escalate_human.
    raw = invoke_text(
        [system_msg, human_msg],
        fallback='{"decision": "escalate_human", "reasoning": "LLM unavailable — safe fallback to human review."}',
    )

    try:
        # strip accidental markdown fences if model adds them
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        decision = parsed.get("decision", "")
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, AttributeError):
        decision = ""
        reasoning = f"PARSE_FAILURE: {raw}"

    if decision not in ALLOWED_DECISIONS:
        # fail safe: don't let an invalid/hallucinated action reach Act node
        decision = "escalate_human"
        reasoning = f"Fallback — invalid/unparsed decision. Raw: {raw[:200]}"

    return _apply_decision(state, txn, decision, reasoning)


def _apply_decision(state, txn, decision, reasoning):
    """Run the compliance guardrails on a chosen decision and commit it to state."""
    guard = enforce_action_compliance(decision, txn)
    state["decision_overridden"] = guard["overridden"]
    if guard["overridden"]:
        reasoning = f"{reasoning} | COMPLIANCE OVERRIDE: {decision} -> {guard['decision']}"
    for note in guard["notes"]:
        state["compliance_notes"] = state.get("compliance_notes", []) + [note]

    state["decision"] = guard["decision"]
    state["decision_reasoning"] = reasoning
    _log(f"[Decide] {guard['decision']} — {reasoning}")
    return state


def act_node(state: RecoveryState) -> RecoveryState:
    """Execute the chosen intervention via MCP tool (simulated Razorpay API)."""
    txn = state["txn"]
    decision = state["decision"]
    result = _run_action(decision, txn)
    state["action_result"] = result
    PRIORS.record(txn.get("failure_code", ""), decision, bool(result.get("success")))
    status = "SUCCESS" if result["success"] else "NO RECOVERY"
    _log(
        f"[Act] {decision} - {status} - Rs {result['amount_recovered']} "
        f"(attempt retry_count={txn.get('retry_count', 0)})"
    )

    # Send the customer message (simulated outbox) for messaging actions.
    if decision in MESSAGING_ACTIONS:
        notif = _outbox.send(txn, decision)
        state["notifications"] = state.get("notifications", []) + [notif]
        result["notification"] = {
            "notif_id": notif["notif_id"], "channel": notif["channel"], "lang": notif["lang"],
        }
        _log(f"[Notify] {notif['channel']}/{notif['lang']} — \"{notif['body'][:70]}...\"")

    # Promise-to-pay for overdue invoices (first touch only).
    if txn.get("failure_code") == "invoice_unpaid" and not state.get("ptp") \
            and decision in ("send_reminder", "escalate_human"):
        state["ptp"] = record_ptp(txn)
        _log(f"[PTP] promise-to-pay recorded — due {state['ptp']['ptp_date']}")

    # Record this attempt in the audit log immediately (captures every retry attempt,
    # not just the final one).
    attempt_entry = {
        "txn_id": txn["txn_id"],
        "diagnosis": state.get("diagnosis"),
        "decision": state.get("decision"),
        "decision_reasoning": state.get("decision_reasoning"),
        "action_result": result,
        "retry_count_at_attempt": txn.get("retry_count", 0),
        "compliance_notes": list(state.get("compliance_notes", [])),
        "notifications_sent": len(state.get("notifications", [])),
        "timestamp": datetime.now().isoformat(),
    }
    state["audit_log"] = state.get("audit_log", []) + [attempt_entry]
    return state


def log_node(state: RecoveryState) -> RecoveryState:
    """Append final summary audit entry for this transaction."""
    txn = state["txn"]
    entry = {
        "txn_id": txn["txn_id"],
        "entry_type": "final_summary",
        "diagnosis": state.get("diagnosis"),
        "decision": state.get("decision"),
        "decision_reasoning": state.get("decision_reasoning"),
        "action_result": state.get("action_result"),
        "stop_reason": state.get("stop_reason"),
        "final_retry_count": txn.get("retry_count", 0),
        "compliance_notes": list(state.get("compliance_notes", [])),
        "notifications_sent": len(state.get("notifications", [])),
        "ptp": state.get("ptp"),
        "timestamp": datetime.now().isoformat(),
    }
    state["audit_log"] = state.get("audit_log", []) + [entry]
    _log(f"[Log] final entry recorded for {txn['txn_id']}")
    return state


# Actions that get one bounded follow-up if the first attempt fails (KB: "max 2
# nudges"). `retry` is handled separately against the compliance cap; a failed
# `escalate_human` is terminal (a human owns it now).
_SECOND_TOUCH = {"send_reminder", "apply_discount", "request_mandate_renewal"}


def route_after_act(state: RecoveryState) -> str:
    """
    Conditional edge after Act. Loop back to stop_check for another attempt when:
      - decision was 'retry', it failed, and retries remain below the code's cap; or
      - decision was a nudge/renewal, it failed, and only one attempt has been made.
    Otherwise -> log (done).
    """
    txn = state["txn"]
    decision = state.get("decision")
    result = state.get("action_result", {})
    if result.get("success"):
        return "log"

    done = txn.get("retry_count", 0)

    if decision == "retry" and done < retry_cap(txn.get("failure_code", "")):
        txn["retry_count"] = done + 1
        _log(f"[Route] retry failed — looping back (attempt {done + 2})")
        return "stop_check"

    if decision in _SECOND_TOUCH and done < 1:
        txn["retry_count"] = done + 1
        _log(f"[Route] {decision} failed — one follow-up attempt")
        return "stop_check"

    return "log"


def route_after_stop_check(state: RecoveryState) -> str:
    """Conditional edge: skip to log if halted, else continue to diagnose."""
    return "log" if state.get("stop_reason") else "diagnose"
