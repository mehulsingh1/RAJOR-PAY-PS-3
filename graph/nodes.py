"""
LangGraph node functions.
Step 4: Diagnose + Decide now use real RAG retrieval + Groq LLM reasoning.
"""

import json
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import RecoveryState
from llm.client import llm
from rag.retriever import retrieve_context
from mcp_tools.tools import execute_action

ALLOWED_DECISIONS = [
    "retry",
    "send_reminder",
    "apply_discount",
    "escalate_human",
    "request_mandate_renewal",
]


def detect_node(state: RecoveryState) -> RecoveryState:
    """Mark transaction as at-risk. Pass-through for now."""
    print(f"[Detect] txn_id={state['txn']['txn_id']} amount={state['txn']['amount']}")
    return state


def stop_check_node(state: RecoveryState) -> RecoveryState:
    """Check compliance/business stopping rules before acting."""
    txn = state["txn"]
    stop_reason = None

    if txn.get("do_not_contact"):
        stop_reason = "do_not_contact_flag"
    elif txn.get("retry_count", 0) >= 3:
        stop_reason = "max_retries_reached"

    state["stop_reason"] = stop_reason
    if stop_reason:
        print(f"[StopCheck] HALT — {stop_reason}")
    else:
        print("[StopCheck] Clear to proceed")
    return state


def diagnose_node(state: RecoveryState) -> RecoveryState:
    """Retrieve KB context and ask LLM to reason about root cause."""
    txn = state["txn"]

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

    response = llm.invoke([system_msg, human_msg])
    state["diagnosis"] = response.content.strip()
    print(f"[Diagnose] {state['diagnosis']}")
    return state


def decide_node(state: RecoveryState) -> RecoveryState:
    """Ask LLM to pick ONE intervention from the allowed list, as structured JSON."""
    txn = state["txn"]

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

    response = llm.invoke([system_msg, human_msg])
    raw = response.content.strip()

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

    state["decision"] = decision
    state["decision_reasoning"] = reasoning
    print(f"[Decide] {decision} — {reasoning}")
    return state


def act_node(state: RecoveryState) -> RecoveryState:
    """Execute the chosen intervention via MCP tool (simulated Razorpay API)."""
    txn = state["txn"]
    result = execute_action(state["decision"], txn)
    state["action_result"] = result
    status = "SUCCESS" if result["success"] else "NO RECOVERY"
    print(
        f"[Act] {state['decision']} — {status} — ₹{result['amount_recovered']} "
        f"(attempt retry_count={txn.get('retry_count', 0)})"
    )

    # Record this attempt in the audit log immediately (captures every retry attempt,
    # not just the final one).
    attempt_entry = {
        "txn_id": txn["txn_id"],
        "diagnosis": state.get("diagnosis"),
        "decision": state.get("decision"),
        "decision_reasoning": state.get("decision_reasoning"),
        "action_result": result,
        "retry_count_at_attempt": txn.get("retry_count", 0),
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
        "timestamp": datetime.now().isoformat(),
    }
    state["audit_log"] = state.get("audit_log", []) + [entry]
    print(f"[Log] final entry recorded for {txn['txn_id']}")
    return state


def route_after_act(state: RecoveryState) -> str:
    """
    Conditional edge after Act.
    If decision was 'retry', it failed, and retries remain (< 3) -> loop back
    to stop_check for another attempt. Otherwise -> log (done).
    """
    txn = state["txn"]
    decision = state.get("decision")
    result = state.get("action_result", {})

    if decision == "retry" and not result.get("success") and txn.get("retry_count", 0) < 3:
        txn["retry_count"] = txn.get("retry_count", 0) + 1
        print(f"[Route] Retry failed — looping back, retry_count now {txn['retry_count']}")
        return "stop_check"

    return "log"


def route_after_stop_check(state: RecoveryState) -> str:
    """Conditional edge: skip to log if halted, else continue to diagnose."""
    return "log" if state.get("stop_reason") else "diagnose"