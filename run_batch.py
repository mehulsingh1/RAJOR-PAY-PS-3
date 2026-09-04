"""
Runs the full recovery pipeline over the entire dataset (or a chosen N),
headless (no UI), saves all results + computed metrics to disk.

Usage:
    python run_batch.py            # full 500
    python run_batch.py 100        # first 100 only
"""

import sys
import json
import os

import pandas as pd

from graph.build_graph import build_graph
from metrics.engine import compute_metrics

DATA_PATH = "data/failed_transactions.csv"
RESULTS_DIR = "results"
RESULTS_PATH = os.path.join(RESULTS_DIR, "batch_results.json")
METRICS_PATH = os.path.join(RESULTS_DIR, "batch_metrics.json")


def run_batch(n: int = None):
    df = pd.read_csv(DATA_PATH)
    if n:
        df = df.head(n)
    batch = df.to_dict(orient="records")

    app = build_graph()
    results = []

    print(f"Running batch of {len(batch)} transactions...\n")

    for i, txn in enumerate(batch, 1):
        initial_state = {
            "txn": txn,
            "diagnosis": "",
            "rag_context": "",
            "decision": "",
            "decision_reasoning": "",
            "stop_reason": None,
            "action_result": {},
            "audit_log": [],
        }
        try:
            final_state = app.invoke(initial_state, config={"recursion_limit": 50})
            results.append(final_state)
        except Exception as e:
            print(f"[ERROR] txn {txn['txn_id']} failed: {e}")

        if i % 10 == 0 or i == len(batch):
            print(f"  ...processed {i}/{len(batch)}")

    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)

    metrics = compute_metrics(results)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nSaved {len(results)} results -> {RESULTS_PATH}")
    print(f"Saved metrics -> {METRICS_PATH}\n")
    print("--- Summary ---")
    print(json.dumps(metrics, indent=2))

    return results, metrics


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_batch(n)
