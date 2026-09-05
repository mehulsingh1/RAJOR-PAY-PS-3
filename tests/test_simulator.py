"""Payment simulator: simulator/engine.py"""

from simulator.engine import PaymentSimulator
from data.live_store import TXN_COLUMNS


def test_deterministic():
    a = list(PaymentSimulator(seed=3).run(200))
    b = list(PaymentSimulator(seed=3).run(200))
    assert [e["type"] for e in a] == [e["type"] for e in b]


def test_fail_rate_in_band():
    sim = PaymentSimulator(seed=1, fail_rate=0.17)
    list(sim.run(3000))
    assert 0.13 < sim.failures / sim.attempts < 0.21


def test_failed_txn_has_all_columns():
    sim = PaymentSimulator(seed=5)
    for e in sim.run(500):
        if e["type"] == "payment_failed":
            for col in TXN_COLUMNS:
                assert col in e["txn"]
            return
    raise AssertionError("expected at least one failure in 500 ticks")


def test_stats():
    sim = PaymentSimulator(seed=9)
    list(sim.run(100))
    s = sim.stats()
    assert s["attempts"] == 100 and s["failures"] == sim.failures
