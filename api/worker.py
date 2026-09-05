"""
RecoveryService — drives the simulator and the agent worker for the live demo.

- a simulator loop appends failed payments to the LiveStore on a timer
- a worker loop pulls the highest-priority pending transaction and runs the
  LangGraph recovery agent on it
- transactions the agent escalates pause in a human-in-the-loop queue
- every step publishes an event on the bus for the SSE stream
"""

import asyncio
import os

from api.events import BUS
from baseline.strategy import run_all_baselines
from data.live_store import LiveStore
from graph import nodes
from graph.build_graph import build_graph
from graph.detection import prioritized, score_transaction
from learning.priors import PRIORS
from metrics.engine import compare_strategies, compute_metrics
from mcp_tools.tools import execute_action
from notifications.outbox import Outbox

LIVE_CSV = os.getenv("LIVE_CSV", "data/live_transactions.csv")
NOTIF_CSV = os.getenv("NOTIF_CSV", "data/notifications.csv")


def _row_to_txn(row: dict) -> dict:
    def num(v, cast, default):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default
    return {
        "txn_id": row["txn_id"],
        "user_id": row.get("user_id", ""),
        "amount": num(row.get("amount"), float, 0.0),
        "payment_method": row.get("payment_method", ""),
        "failure_code": row.get("failure_code", ""),
        "failure_stage": row.get("failure_stage", ""),
        "retry_count": num(row.get("retry_count"), int, 0),
        "do_not_contact": str(row.get("do_not_contact", "")).lower() in ("true", "1", "yes"),
        "customer_segment": row.get("customer_segment", "regular"),
        "preferred_language": row.get("preferred_language", "en"),
        "days_overdue": num(row.get("days_overdue"), float, None),
    }


def _fresh_state(txn: dict) -> dict:
    return {
        "txn": txn, "risk_score": 0.0, "risk_tier": "", "risk_reason": "",
        "expected_recoverable": 0.0, "diagnosis": "", "rag_context": "",
        "decision": "", "decision_reasoning": "", "decision_overridden": False,
        "stop_reason": None, "compliance_notes": [], "notifications": [],
        "ptp": None, "action_result": {}, "audit_log": [],
    }


class RecoveryService:
    def __init__(self):
        self.store = LiveStore(LIVE_CSV)
        self.outbox = Outbox(NOTIF_CSV)
        nodes.set_outbox(self.outbox)
        self.graph = build_graph()
        self.sim = None
        self.queue: dict[str, dict] = {}   # txn_id -> {row, state}
        self.running = False
        self.rate = 1.0
        self._tasks: list[asyncio.Task] = []

    # --- lifecycle -----------------------------------------------------
    async def start(self, rate: float = 1.0, seed: int = 7):
        if self.running:
            return
        from simulator.engine import PaymentSimulator
        self.rate = max(0.1, min(10.0, rate))
        if self.sim is None:
            self.sim = PaymentSimulator(seed=seed)
        self.running = True
        self._tasks = [asyncio.create_task(self._sim_loop()),
                       asyncio.create_task(self._worker_loop())]
        BUS.publish("simulation_started", {"rate": self.rate})

    async def stop(self):
        self.running = False
        for t in self._tasks:
            t.cancel()
        self._tasks = []
        BUS.publish("simulation_stopped", {})

    def reset(self):
        self.store.reset()
        self.outbox.reset()
        PRIORS.reset()
        self.sim = None
        self.queue.clear()
        BUS.publish("reset", {})

    # --- loops -----------------------------------------------------
    async def _sim_loop(self):
        try:
            while self.running:
                evt = self.sim.tick()
                if evt["type"] == "payment_failed":
                    txn = evt["txn"]
                    a = score_transaction(txn)
                    self.store.append_failure({**txn, "risk_score": a["risk_score"]})
                    self.store.update(txn["txn_id"], risk_score=a["risk_score"])
                    BUS.publish("payment_failed", {
                        "txn_id": txn["txn_id"], "amount": txn["amount"],
                        "failure_code": txn["failure_code"], "risk_score": a["risk_score"],
                    })
                else:
                    BUS.publish("payment_ok", {"attempts": evt["attempts"]})
                await asyncio.sleep(1.0 / self.rate)
        except asyncio.CancelledError:
            pass

    async def _worker_loop(self):
        loop = asyncio.get_event_loop()
        try:
            while self.running:
                pend = [r for r in self.store.pending()]
                if not pend:
                    await asyncio.sleep(0.4)
                    continue
                row = prioritized([_row_to_txn(r) for r in pend])[0]
                self.store.update(row["txn_id"], status="queued")
                await loop.run_in_executor(None, self._process, row["txn_id"])
        except asyncio.CancelledError:
            pass

    # --- processing -----------------------------------------------------
    def _process(self, txn_id: str):
        row = self.store.get(txn_id)
        if not row:
            return
        txn = _row_to_txn(row)
        self.store.update(txn_id, status="diagnosing")
        BUS.publish("agent_step", {"txn_id": txn_id, "step": "diagnosing"})

        final = self.graph.invoke(_fresh_state(txn), config={"recursion_limit": 60})
        decision = final.get("decision")
        diagnosis = final.get("diagnosis", "")
        notifs = final.get("notifications", [])
        flags = final.get("compliance_notes", [])
        ptp = final.get("ptp")

        common = dict(
            diagnosis=diagnosis, decision=decision or "",
            attempts=int(txn.get("retry_count", 0)) + 1,
            compliance_flags=" | ".join(flags),
            notifications_sent=len(notifs),
            ptp_date=(ptp or {}).get("ptp_date", ""),
            ptp_status=(ptp or {}).get("ptp_status", ""),
            last_action=decision or "", last_channel=(notifs[-1]["channel"] if notifs else ""),
        )
        for n in notifs:
            BUS.publish("notification", n)
        for f in flags:
            BUS.publish("compliance", {"txn_id": txn_id, "note": f})

        if decision == "escalate_human" and not final.get("stop_reason"):
            self.store.update(txn_id, status="escalated", **common)
            self.queue[txn_id] = {"row": self.store.get(txn_id), "txn": txn}
            BUS.publish("escalation", {"txn_id": txn_id, "amount": txn["amount"],
                                       "diagnosis": diagnosis})
            return

        self._finalize(txn_id, txn, final.get("action_result", {}),
                       final.get("stop_reason"), common)

    def _finalize(self, txn_id, txn, result, stop_reason, common):
        gross = float(result.get("amount_recovered", 0.0) or 0.0)
        cost = float(result.get("intervention_cost", 0.0) or 0.0)
        if stop_reason:
            status = f"halted:{stop_reason}"
        elif result.get("success"):
            status = "recovered"
        else:
            status = "lost"
        self.store.update(txn_id, status=status, gross_recovered=round(gross, 2),
                          intervention_cost=round(cost, 2),
                          net_recovered=round(gross - cost, 2), **common)
        BUS.publish("resolved", {"txn_id": txn_id, "status": status,
                                 "gross": round(gross, 2), "net": round(gross - cost, 2)})

    # --- human-in-the-loop -----------------------------------------------------
    def resolve_queue(self, txn_id: str, action: str, override: str | None = None) -> dict:
        item = self.queue.pop(txn_id, None)
        if not item:
            return {"error": "not in queue"}
        txn = item["txn"]
        if action == "reject":
            self.store.update(txn_id, status="lost", last_action="human_reject")
            BUS.publish("queue_resolved", {"txn_id": txn_id, "action": "reject"})
            return {"txn_id": txn_id, "status": "lost"}
        chosen = override if action == "override" and override else "escalate_human"
        result = execute_action(chosen, txn)
        PRIORS.record(txn.get("failure_code", ""), chosen, bool(result.get("success")))
        common = dict(decision=chosen, last_action=f"human_{action}:{chosen}",
                      attempts=int(txn.get("retry_count", 0)) + 1)
        self._finalize(txn_id, txn, result, None, common)
        BUS.publish("queue_resolved", {"txn_id": txn_id, "action": action, "chosen": chosen,
                                       "success": bool(result.get("success"))})
        return {"txn_id": txn_id, "chosen": chosen, "success": bool(result.get("success"))}

    # --- snapshots -----------------------------------------------------
    def metrics(self) -> dict:
        rows = self.store.all()
        results = [self._row_as_result(r) for r in rows if _terminal(r.get("status", ""))]
        if not results:
            return {"empty": True, "sim": self.sim.stats() if self.sim else {}}
        m = compute_metrics(results)
        baselines = run_all_baselines([r["txn"] for r in results])
        cmp = compare_strategies(results, baselines)
        return {"empty": False, "metrics": m, "comparison": cmp,
                "sim": self.sim.stats() if self.sim else {},
                "status_counts": self.store.count_by_status(),
                "queue_size": len(self.queue)}

    @staticmethod
    def _row_as_result(row: dict) -> dict:
        txn = _row_to_txn(row)
        gross = float(row.get("gross_recovered") or 0.0)
        cost = float(row.get("intervention_cost") or 0.0)
        st = row.get("status", "")
        return {
            "txn": txn,
            "decision": row.get("decision") or "none",
            "decision_overridden": bool(row.get("compliance_flags")),
            "stop_reason": st.split("halted:")[1] if st.startswith("halted:") else None,
            "action_result": {"success": st == "recovered", "amount_recovered": gross,
                              "intervention_cost": cost},
        }


def _terminal(status: str) -> bool:
    return status == "recovered" or status == "lost" or status.startswith("halted:")


SERVICE = RecoveryService()
