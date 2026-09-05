"""
Promise-to-pay tracking for overdue invoices (Track 3 PS lists it explicitly).

When the agent nudges an `invoice_unpaid` customer it records a PTP: a date by
which payment is expected, tiered by how overdue the invoice already is. A later
check (the worker, Step C) flips the status to `kept` or `breached`; a breach
escalates to a human.
"""

from datetime import datetime, timedelta, timezone

# days_overdue tier -> days we give the customer to pay
PTP_WINDOW = [(15, 7), (45, 5), (90, 3), (float("inf"), 2)]


def _window_days(days_overdue: float) -> int:
    for threshold, window in PTP_WINDOW:
        if days_overdue <= threshold:
            return window
    return 2


def record_ptp(txn: dict, now: datetime | None = None) -> dict:
    """Create a promise-to-pay commitment for an overdue invoice."""
    now = now or datetime.now(timezone.utc)
    try:
        d = float(txn.get("days_overdue") or 0)
    except (TypeError, ValueError):
        d = 0.0
    window = _window_days(d)
    return {
        "ptp_date": (now + timedelta(days=window)).date().isoformat(),
        "ptp_window_days": window,
        "ptp_status": "pending",
    }


def check_ptp(ptp_date: str, paid: bool, now: datetime | None = None) -> str:
    """Resolve a pending PTP. Returns 'kept', 'pending', or 'breached'."""
    if paid:
        return "kept"
    now = now or datetime.now(timezone.utc)
    try:
        due = datetime.fromisoformat(ptp_date).replace(tzinfo=timezone.utc)
    except ValueError:
        return "pending"
    return "breached" if now.date() > due.date() else "pending"
