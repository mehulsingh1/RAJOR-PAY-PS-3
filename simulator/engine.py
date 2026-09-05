"""
PaymentSimulator — a fake Razorpay payment stream for the live demo.

Each tick is one payment attempt. ~FAIL_RATE of them fail (using the same
distributions as data/generate_dataset), and a failed attempt produces a full
transaction row for the agent to work. Successful attempts are just counted.

Deterministic for a given seed. The API layer (Step C) drives ticks on a timer
and appends failures to the LiveStore.
"""

import random
from datetime import datetime, timezone

from data.generate_dataset import (
    CODE_STAGE, CODE_WEIGHTS, LANG_WEIGHTS, METHOD_WEIGHTS, NO_RETRY_CODES,
    _amount, _method, _weighted,
)

FAIL_RATE = 0.17
DNC_RATE = 0.06
HIGH_VALUE_RATE = 0.18


class PaymentSimulator:
    def __init__(self, seed: int = 7, fail_rate: float = FAIL_RATE):
        self.rng = random.Random(seed)
        self.fail_rate = fail_rate
        self.attempts = 0
        self.failures = 0
        self._users = [f"user_{self.rng.randbytes(4).hex()}" for _ in range(120)]

    def _make_failed_txn(self) -> dict:
        rng = self.rng
        code = _weighted(rng, CODE_WEIGHTS)
        is_invoice = code == "invoice_unpaid"
        segment = "high_value" if rng.random() < HIGH_VALUE_RATE else "regular"
        return {
            "txn_id": f"txn_{rng.randbytes(5).hex()}",
            "user_id": rng.choice(self._users),
            "amount": _amount(rng, segment, is_invoice),
            "payment_method": _method(rng, code),
            "failure_code": code,
            "failure_stage": CODE_STAGE[code],
            "retry_count": 0 if code in NO_RETRY_CODES else (1 if rng.random() < 0.12 else 0),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "do_not_contact": rng.random() < DNC_RATE,
            "customer_segment": segment,
            "preferred_language": _weighted(rng, LANG_WEIGHTS),
            "days_overdue": round(min(120, rng.expovariate(1 / 32) + 1), 1) if is_invoice else "",
        }

    def tick(self) -> dict:
        """One payment attempt. Returns an event describing what happened."""
        self.attempts += 1
        if self.rng.random() < self.fail_rate:
            self.failures += 1
            return {"type": "payment_failed", "txn": self._make_failed_txn(),
                    "attempts": self.attempts, "failures": self.failures}
        return {"type": "payment_ok", "attempts": self.attempts, "failures": self.failures}

    def run(self, n: int):
        """Yield n ticks (used for tests / headless runs)."""
        for _ in range(n):
            yield self.tick()

    def stats(self) -> dict:
        return {
            "attempts": self.attempts,
            "failures": self.failures,
            "fail_rate_pct": round(100 * self.failures / self.attempts, 1) if self.attempts else 0.0,
        }
