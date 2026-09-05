"""
Synthetic at-risk transaction generator.

Produces data/transactions_v2.csv (default 200 rows) from documented, seeded
distributions. The goal is a *realistic* revenue-at-risk book, not one tuned to
flatter the agent — the mix, amounts and failure reasons below are the knobs and
they are all visible here.

Run:
    python data/generate_dataset.py            # 200 rows -> data/transactions_v2.csv
    python data/generate_dataset.py 500 out.csv
"""

import csv
import math
import random
import sys
from datetime import datetime, timedelta

SEED = 20260905

# failure_code -> failure_stage (from rag/knowledge_base.json)
CODE_STAGE = {
    "insufficient_funds": "payment_failure",
    "bank_decline": "payment_failure",
    "card_expired": "payment_failure",
    "issuer_timeout": "payment_failure",
    "gateway_timeout": "checkout_abandon",
    "otp_timeout": "checkout_abandon",
    "user_dropped": "checkout_abandon",
    "mandate_lapsed": "subscription_failure",
    "invoice_unpaid": "receivable_overdue",
}

# Realistic frequency mix (sums to 1.0).
CODE_WEIGHTS = {
    "insufficient_funds": 0.22,
    "invoice_unpaid": 0.16,
    "bank_decline": 0.12,
    "issuer_timeout": 0.10,
    "card_expired": 0.09,
    "otp_timeout": 0.08,
    "mandate_lapsed": 0.08,
    "user_dropped": 0.08,
    "gateway_timeout": 0.07,
}

METHOD_WEIGHTS = {"upi": 0.42, "card": 0.28, "netbanking": 0.16, "mandate": 0.14}

# log-normal amount medians (INR) by segment; invoices are much larger.
AMOUNT_MEDIAN = {
    ("regular", False): 1200, ("high_value", False): 9000,
    ("regular", True): 22000, ("high_value", True): 110000,  # True = invoice
}
AMOUNT_SIGMA = 0.7

RETRY_DIST = [(0, 0.85), (1, 0.11), (2, 0.04)]  # retry-eligible codes only
NO_RETRY_CODES = {"card_expired", "mandate_lapsed"}
DNC_RATE = 0.06
HIGH_VALUE_RATE = 0.18
LANG_WEIGHTS = {"hinglish": 0.6, "en": 0.4}  # realistic for India retail


def _weighted(rng, weights: dict):
    r, acc = rng.random(), 0.0
    for k, w in weights.items():
        acc += w
        if r <= acc:
            return k
    return next(reversed(weights))


def _method(rng, code):
    if code == "mandate_lapsed":
        return "mandate"
    if code == "card_expired":
        return "card"
    if code == "invoice_unpaid":
        return rng.choice(["netbanking", "upi", "netbanking"])
    return _weighted(rng, METHOD_WEIGHTS)


def _amount(rng, segment, is_invoice):
    median = AMOUNT_MEDIAN[(segment, is_invoice)]
    return round(math.exp(rng.gauss(math.log(median), AMOUNT_SIGMA)), 2)


def _retry_count(rng, code):
    if code in NO_RETRY_CODES:
        return 0
    r, acc = rng.random(), 0.0
    for value, weight in RETRY_DIST:
        acc += weight
        if r <= acc:
            return value
    return 0


def generate(n: int = 200, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    users = [f"user_{rng.randbytes(4).hex()}" for _ in range(max(1, int(n * 0.7)))]
    now = datetime(2026, 9, 5, 12, 0, 0)
    rows = []
    for _ in range(n):
        code = _weighted(rng, CODE_WEIGHTS)
        is_invoice = code == "invoice_unpaid"
        segment = "high_value" if rng.random() < HIGH_VALUE_RATE else "regular"
        dnc = rng.random() < (DNC_RATE + (0.03 if code == "user_dropped" else 0))
        rows.append({
            "txn_id": f"txn_{rng.randbytes(5).hex()}",
            "user_id": rng.choice(users),
            "amount": _amount(rng, segment, is_invoice),
            "payment_method": _method(rng, code),
            "failure_code": code,
            "failure_stage": CODE_STAGE[code],
            "retry_count": _retry_count(rng, code),
            "timestamp": (now - timedelta(minutes=rng.randint(0, 14 * 24 * 60))).isoformat(),
            "do_not_contact": dnc,
            "customer_segment": segment,
            "preferred_language": _weighted(rng, LANG_WEIGHTS),
            "days_overdue": round(min(120, rng.expovariate(1 / 32) + 1), 1) if is_invoice else "",
        })
    return rows


def _report(rows: list[dict]) -> None:
    from collections import Counter
    n = len(rows)
    print(f"\n{n} transactions generated\n" + "-" * 40)
    for field in ("failure_code", "failure_stage", "payment_method", "customer_segment"):
        c = Counter(r[field] for r in rows)
        print(f"{field}:")
        for k, v in c.most_common():
            print(f"    {k:20} {v:4}  ({v / n:.0%})")
    amts = sorted(r["amount"] for r in rows)
    print(f"amount: min {amts[0]:,.0f} / median {amts[n // 2]:,.0f} / max {amts[-1]:,.0f}")
    print(f"do_not_contact: {sum(bool(r['do_not_contact']) for r in rows)} ({sum(bool(r['do_not_contact']) for r in rows) / n:.0%})")
    print(f"retry_count>0: {sum(r['retry_count'] > 0 for r in rows)}")
    inv = [r['days_overdue'] for r in rows if r['failure_code'] == 'invoice_unpaid']
    if inv:
        print(f"invoice days_overdue: min {min(inv):.0f} / mean {sum(inv) / len(inv):.0f} / max {max(inv):.0f}")


FIELDNAMES = [
    "txn_id", "user_id", "amount", "payment_method", "failure_code", "failure_stage",
    "retry_count", "timestamp", "do_not_contact", "customer_segment",
    "preferred_language", "days_overdue",
]


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    out = sys.argv[2] if len(sys.argv) > 2 else "data/transactions_v2.csv"
    rows = generate(n)
    write_csv(rows, out)
    _report(rows)
    print(f"\nwrote {out}")
