"""
Shared state object passed between all LangGraph nodes.
"""

from typing import TypedDict, Optional


class RecoveryState(TypedDict):
    txn: dict                    # current transaction row (from batch)
    diagnosis: str                # root cause reasoning (Diagnose node)
    rag_context: str              # retrieved KB context (Diagnose node)
    decision: str                 # chosen intervention (Decide node)
    decision_reasoning: str       # why the LLM chose this decision
    stop_reason: Optional[str]    # reason StopCheck halted flow, else None
    action_result: dict           # outcome of Act node
    audit_log: list               # accumulated audit entries for this txn