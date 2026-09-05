"""
Shared state object passed between all LangGraph nodes.
"""

from typing import TypedDict, Optional


class RecoveryState(TypedDict):
    txn: dict                    # current transaction row (from batch)
    risk_score: float             # 0-100 revenue-at-risk priority (Detect node)
    risk_tier: str                # "high" | "medium" | "low" (Detect node)
    risk_reason: str              # human-readable "why flagged" (Detect node)
    expected_recoverable: float   # ₹ realistically recoverable (Detect node)
    diagnosis: str                # root cause reasoning (Diagnose node)
    rag_context: str              # retrieved KB context (Diagnose node)
    decision: str                 # chosen intervention (Decide node, post-compliance)
    decision_reasoning: str       # why the LLM chose this decision
    decision_overridden: bool     # True if a compliance rule changed the decision
    stop_reason: Optional[str]    # reason StopCheck halted flow, else None
    compliance_notes: list        # compliance rules that fired (halts + overrides)
    action_result: dict           # outcome of Act node
    notifications: list           # simulated messages sent (Act node)
    ptp: Optional[dict]           # promise-to-pay commitment for overdue invoices
    audit_log: list               # accumulated audit entries for this txn