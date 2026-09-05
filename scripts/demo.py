"""
One-command reproducible demo — no LLM, no server, ~2 seconds.

    python -m scripts.demo            # the committed 200-row dataset
    python -m scripts.demo --gen 300  # regenerate a fresh N-row dataset first

Runs the agent (playbook mode) through the full pipeline — detection, compliance,
second-touch, notifications, cost — and prints the honest agent-vs-baseline
comparison, gross and net. On small samples the margin narrows (baseline
"always remind" is genuinely decent); the committed 200-row set is the headline.
"""

import os
import sys

os.environ.setdefault("AGENT_MODE", "playbook")
os.environ.setdefault("RECOVERY_SEED", "42")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from baseline.strategy import run_baseline, policy_label  # noqa: E402
from data.generate_dataset import generate, write_csv  # noqa: E402
from data.loader import load_transactions  # noqa: E402
from graph.detection import prioritized  # noqa: E402
from metrics.engine import compare_strategies  # noqa: E402

PATH = "data/transactions_v2.csv"


def main():
    if "--gen" in sys.argv:
        n = int(sys.argv[sys.argv.index("--gen") + 1])
        write_csv(generate(n), PATH)
    df, _ = load_transactions(PATH)
    rows = prioritized(df.to_dict("records"))

    # "agent" == playbook policy run through the same pipeline as the baselines
    agent = run_baseline(rows, "static_playbook")
    others = {k: run_baseline(rows, k) for k in ("retry_all", "reminder_all")}
    cmp = compare_strategies(agent, others)

    print(f"\n  Revenue Recovery — {len(rows)} at-risk transactions "
          f"(₹{cmp['total_at_risk_amount']:,.0f} at risk)\n" + "  " + "-" * 62)
    for name, r in cmp["by_strategy"].items():
        label = "AI agent (KB policy)" if name == "agent" else policy_label(name)
        print(f"  {label:24}  gross ₹{r['recovered']:>11,.0f}   "
              f"cost ₹{r['intervention_cost']:>7,.0f}   "
              f"NET ₹{r['net_recovered']:>11,.0f}  ({r['net_recovery_rate_pct']}%)")
    u = cmp["agent_uplift_over_best_baseline"]
    print("  " + "-" * 62)
    print(f"  Agent nets ₹{u['extra_net_recovered']:,.0f} more than the best naive "
          f"baseline ({policy_label(u['vs'])})  (+{u['extra_net_rate_pp']} pp)\n")


if __name__ == "__main__":
    main()
