"""
Online learning loop.

The agent records the real outcome of every (failure_code, action) it tries and
keeps a rolling success rate. Once a pair has enough observations, that observed
rate is blended into the simulator's base probability — so the agent's estimate
of "what works" improves over a run. Visible in the dashboard's learning panel.

Deliberately simple: a Beta(1,1)-smoothed rate, blended with a small weight, and
only after MIN_OBS observations so a cold start changes nothing.
"""

import os
import threading

MIN_OBS = 8          # ignore a pair until we've seen it this many times
BLEND_WEIGHT = 0.35  # how far to move base_p toward the observed rate
ENABLED = os.getenv("LEARNING", "1").lower() in ("1", "true", "yes")


class Priors:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str], list[int]] = {}  # (code, action) -> [succ, total]

    def record(self, failure_code: str, action: str, success: bool) -> None:
        with self._lock:
            k = (failure_code, action)
            c = self._counts.setdefault(k, [0, 0])
            c[0] += 1 if success else 0
            c[1] += 1

    def rate(self, failure_code: str, action: str) -> float | None:
        c = self._counts.get((failure_code, action))
        if not c or c[1] < MIN_OBS:
            return None
        return (c[0] + 1) / (c[1] + 2)  # Beta(1,1) smoothing

    def blend(self, base_p: float, failure_code: str, action: str) -> float:
        if not ENABLED:
            return base_p
        observed = self.rate(failure_code, action)
        if observed is None:
            return base_p
        return round((1 - BLEND_WEIGHT) * base_p + BLEND_WEIGHT * observed, 4)

    def snapshot(self) -> list[dict]:
        with self._lock:
            out = []
            for (code, action), (succ, total) in sorted(self._counts.items()):
                out.append({
                    "failure_code": code, "action": action,
                    "successes": succ, "total": total,
                    "observed_rate": round((succ + 1) / (total + 2), 3),
                    "active": total >= MIN_OBS,
                })
            return out

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


PRIORS = Priors()
