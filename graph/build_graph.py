"""
Wires nodes into the LangGraph StateGraph and compiles it.
"""

from langgraph.graph import StateGraph, END

from graph.state import RecoveryState
from graph.nodes import (
    detect_node,
    stop_check_node,
    diagnose_node,
    decide_node,
    act_node,
    log_node,
    route_after_stop_check,
    route_after_act,
)


def build_graph():
    graph = StateGraph(RecoveryState)

    graph.add_node("detect", detect_node)
    graph.add_node("stop_check", stop_check_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("decide", decide_node)
    graph.add_node("act", act_node)
    graph.add_node("log", log_node)

    graph.set_entry_point("detect")

    graph.add_edge("detect", "stop_check")

    graph.add_conditional_edges(
        "stop_check",
        route_after_stop_check,
        {
            "log": "log",
            "diagnose": "diagnose",
        },
    )

    graph.add_edge("diagnose", "decide")
    graph.add_edge("decide", "act")

    graph.add_conditional_edges(
        "act",
        route_after_act,
        {
            "stop_check": "stop_check",  # loop back for another retry attempt
            "log": "log",
        },
    )

    graph.add_edge("log", END)

    return graph.compile()


if __name__ == "__main__":
    # Quick manual test with one fake transaction
    app = build_graph()

    test_txn = {
        "txn_id": "txn_test001",
        "user_id": "user_test",
        "amount": 1500.0,
        "payment_method": "card",
        "failure_code": "insufficient_funds",
        "failure_stage": "payment_failure",
        "retry_count": 0,
        "do_not_contact": False,
    }

    initial_state: RecoveryState = {
        "txn": test_txn,
        "diagnosis": "",
        "rag_context": "",
        "decision": "",
        "decision_reasoning": "",
        "stop_reason": None,
        "action_result": {},
        "audit_log": [],
    }

    result = app.invoke(initial_state)
    print("\n--- Final State ---")
    print(result)