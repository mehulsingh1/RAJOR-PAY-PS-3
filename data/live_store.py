"""
LiveStore — the single source of truth for the streaming demo.

The simulator appends failed transactions here; the agent worker updates their
status and outcome in place. It is a plain CSV so a judge can open it, and every
mutation is flushed immediately. A lock guards the simulator thread and the
worker thread.
"""

import csv
import threading
from datetime import datetime, timezone

# Base transaction columns (match data/generate_dataset.FIELDNAMES) + agent columns.
TXN_COLUMNS = [
    "txn_id", "user_id", "amount", "payment_method", "failure_code", "failure_stage",
    "retry_count", "timestamp", "do_not_contact", "customer_segment",
    "preferred_language", "days_overdue",
]
AGENT_COLUMNS = [
    "status", "created_at", "updated_at", "attempts", "last_action", "last_channel",
    "gross_recovered", "intervention_cost", "net_recovered", "diagnosis", "decision",
    "compliance_flags", "notifications_sent", "ptp_date", "ptp_status", "risk_score",
]
COLUMNS = TXN_COLUMNS + AGENT_COLUMNS

# Lifecycle values for `status`.
PENDING = {"failed", "queued"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveStore:
    def __init__(self, path: str = "data/live_transactions.csv"):
        self.path = path
        self._lock = threading.Lock()
        self._rows: dict[str, dict] = {}
        self._load()

    # --- persistence -----------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._rows[row["txn_id"]] = row
        except FileNotFoundError:
            pass

    def _flush(self) -> None:
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for row in self._rows.values():
                w.writerow(row)

    # --- mutations -----------------------------------------------------
    def append_failure(self, txn: dict) -> dict:
        """Add a newly failed transaction from the simulator."""
        with self._lock:
            row = {c: "" for c in COLUMNS}
            row.update({k: txn.get(k, "") for k in TXN_COLUMNS})
            row.update({
                "status": "failed", "created_at": _now(), "updated_at": _now(),
                "attempts": 0, "notifications_sent": 0, "ptp_status": "",
                "gross_recovered": 0, "intervention_cost": 0, "net_recovered": 0,
            })
            self._rows[row["txn_id"]] = row
            self._flush()
            return row

    def update(self, txn_id: str, **fields) -> dict | None:
        with self._lock:
            row = self._rows.get(txn_id)
            if row is None:
                return None
            row.update({k: v for k, v in fields.items() if k in COLUMNS})
            row["updated_at"] = _now()
            self._flush()
            return row

    def reset(self) -> None:
        with self._lock:
            self._rows.clear()
            self._flush()

    # --- reads -----------------------------------------------------
    def get(self, txn_id: str) -> dict | None:
        return self._rows.get(txn_id)

    def all(self) -> list[dict]:
        return list(self._rows.values())

    def pending(self) -> list[dict]:
        return [r for r in self._rows.values() if r.get("status") in PENDING]

    def count_by_status(self) -> dict:
        out: dict[str, int] = {}
        for r in self._rows.values():
            out[r.get("status", "?")] = out.get(r.get("status", "?"), 0) + 1
        return out
