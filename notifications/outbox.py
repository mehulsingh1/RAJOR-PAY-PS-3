"""
Outbox — the (simulated) send path for recovery messages.

Every message is rendered from notifications/templates.py, costed via
mcp_tools/costs.py, appended to data/notifications.csv, and returned as a record.
Nothing actually leaves the machine unless NOTIFY_REAL=1 and SMTP_* are set
(email only) — the demo runs fully simulated by default.
"""

import csv
import os
import threading
import uuid
from datetime import datetime, timezone

from mcp_tools.costs import CHANNEL_COST, channel_for
from notifications.templates import render

FIELDNAMES = [
    "notif_id", "txn_id", "channel", "lang", "action", "subject", "body",
    "cost", "simulated", "status", "sent_at",
]

REAL_SEND = os.getenv("NOTIFY_REAL", "").lower() in ("1", "true", "yes")


class Outbox:
    def __init__(self, path: str = "data/notifications.csv"):
        self.path = path
        self._lock = threading.Lock()
        self._records: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, newline="", encoding="utf-8") as f:
                self._records = list(csv.DictReader(f))
        except FileNotFoundError:
            pass

    def _flush(self) -> None:
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            w.writeheader()
            w.writerows(self._records)

    def send(self, txn: dict, action: str, channel: str | None = None) -> dict:
        channel = channel or channel_for(action, txn)
        msg = render(txn.get("failure_code", ""), txn, txn.get("preferred_language", "en"))
        rec = {
            "notif_id": uuid.uuid4().hex[:12],
            "txn_id": txn.get("txn_id", ""),
            "channel": channel,
            "lang": msg["lang"],
            "action": action,
            "subject": msg["subject"] if channel == "email" else "",
            "body": msg["body"],
            "cost": round(CHANNEL_COST.get(channel, 0.0), 2),
            "simulated": not (REAL_SEND and channel == "email"),
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if REAL_SEND and channel == "email":
            rec["status"] = _try_real_email(rec)
        with self._lock:
            self._records.append(rec)
            self._flush()
        return rec

    def all(self) -> list[dict]:
        return list(self._records)

    def for_txn(self, txn_id: str) -> list[dict]:
        return [r for r in self._records if r["txn_id"] == txn_id]

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._flush()


def _try_real_email(rec: dict) -> str:
    """Best-effort real email via SMTP env vars. Never raises."""
    import smtplib
    from email.message import EmailMessage

    host, user, pw = (os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
    to = os.getenv("NOTIFY_TO")
    if not all((host, user, pw, to)):
        return "sent"  # fall back to simulated silently
    try:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = user, to, rec["subject"]
        m.set_content(rec["body"])
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(m)
        return "sent_real"
    except Exception:
        return "send_failed"
