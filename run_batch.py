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

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from graph.build_graph import build_graph
from graph.detection import prioritized
from baseline.strategy import run_all_baselines, policy_label
from metrics.engine import compute_metrics, compare_strategies
from data.loader import load_transactions

DATA_PATH = os.getenv("DATASET", "data/transactions_v2.csv")
RESULTS_DIR = "results"
RESULTS_PATH = os.path.join(RESULTS_DIR, "batch_results.json")
METRICS_PATH = os.path.join(RESULTS_DIR, "batch_metrics.json")
COMPARISON_PATH = os.path.join(RESULTS_DIR, "strategy_comparison.json")


def run_batch(n: int = None):
    df, report = load_transactions(DATA_PATH)
    if report["dropped_bad_amount"]:
        print(f"[loader] dropped {report['dropped_bad_amount']} row(s) with a bad amount")
    if n:
        df = df.head(n)
    # Work the highest-value recoverable revenue first.
    batch = prioritized(df.to_dict(orient="records"))

    app = build_graph()
    results = []

    print(f"Running batch of {len(batch)} transactions (priority-ordered)...\n")

    for i, txn in enumerate(batch, 1):
        initial_state = {
            "txn": txn,
            "risk_score": 0.0,
            "risk_tier": "",
            "risk_reason": "",
            "expected_recoverable": 0.0,
            "diagnosis": "",
            "rag_context": "",
            "decision": "",
            "decision_reasoning": "",
            "stop_reason": None,
            "compliance_notes": [],
            "notifications": [],
            "ptp": None,
            "action_result": {},
            "audit_log": [],
        }
        try:
            final_state = app.invoke(initial_state, config={"recursion_limit": 50})
        except Exception as e:
            print(f"[ERROR] txn {txn['txn_id']} failed: {e}")
            final_state = {
                **initial_state,
                "stop_reason": "processing_error",
                "decision": "none",
                "decision_reasoning": f"error: {e}",
            }
        results.append(final_state)

        if i % 10 == 0 or i == len(batch):
            print(f"  ...processed {i}/{len(batch)}")

    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)

    metrics = compute_metrics(results)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    # Baselines: same transactions, same outcome model, no AI decision step.
    print("\nRunning non-AI baselines on the same batch...")
    processed_txns = [r["txn"] for r in results]
    baselines = run_all_baselines(processed_txns)
    comparison = compare_strategies(results, baselines)
    with open(COMPARISON_PATH, "w") as f:
        json.dump(comparison, f, indent=2)

    print(f"\nSaved {len(results)} results -> {RESULTS_PATH}")
    print(f"Saved metrics -> {METRICS_PATH}")
    print(f"Saved strategy comparison -> {COMPARISON_PATH}\n")

    print("--- Agent vs baselines (gross / cost / NET recovered) ---")
    for name, row in comparison["by_strategy"].items():
        label = "AI agent" if name == "agent" else policy_label(name)
        print(
            f"  {label:28} gross Rs {row['recovered']:>12,.0f} ({row['recovery_rate_pct']:>5}%)  "
            f"cost Rs {row['intervention_cost']:>9,.0f}  NET Rs {row['net_recovered']:>12,.0f} "
            f"({row['net_recovery_rate_pct']:>5}%)"
        )
    up = comparison["agent_uplift_over_best_baseline"]
    if up:
        sign = "+" if up["extra_net_recovered"] >= 0 else ""
        print(
            f"\n  vs best baseline ({policy_label(up['vs'])}): "
            f"{sign}Rs {up['extra_net_recovered']:,.0f} net "
            f"({sign}{up['extra_net_rate_pp']} pp), "
            f"gross delta Rs {up['extra_gross_recovered']:,.0f}.\n"
        )

    print("--- Full agent metrics ---")
    print(json.dumps(metrics, indent=2))

    return results, metrics


def _parse_n(argv: list[str]) -> int | None:
    if len(argv) <= 1:
        return None
    try:
        n = int(argv[1])
    except ValueError:
        sys.exit(f"usage: python run_batch.py [N]   (got '{argv[1]}', expected an integer)")
    if n <= 0:
        sys.exit(f"N must be positive (got {n})")
    return n


if __name__ == "__main__":
    run_batch(_parse_n(sys.argv))
