"""
Streamlit UI for the AI Revenue Recovery agent.
Everything runs from the UI — batch size up to the full dataset,
auto-saves results, and can reload the last run instantly.
"""

import json
import os

import streamlit as st
import pandas as pd

from graph.build_graph import build_graph
from metrics.engine import compute_metrics

st.set_page_config(page_title="AI Revenue Recovery Agent", layout="wide")

st.title("AI Revenue Recovery Agent")
st.caption("Razorpay Buildathon — Detect → Diagnose → Decide → Act → Log")

# --- Load data ---
DATA_PATH = "data/failed_transactions.csv"
SAVED_RESULTS_PATH = "results/batch_results.json"

@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)

df = load_data()
TOTAL_TXNS = len(df)

# --- Sidebar controls ---
st.sidebar.header("Batch Controls")
batch_size = st.sidebar.slider(
    "Number of transactions to process",
    min_value=1,
    max_value=TOTAL_TXNS,
    value=min(20, TOTAL_TXNS),
    help="Each transaction costs 2+ LLM calls. Larger batches take longer to run live.",
)
run_button = st.sidebar.button("Run Recovery Batch", type="primary")

st.sidebar.markdown("---")
has_saved = os.path.exists(SAVED_RESULTS_PATH)
if has_saved:
    if st.sidebar.button("Load Last Saved Run"):
        with open(SAVED_RESULTS_PATH) as f:
            st.session_state.results = json.load(f)
        st.sidebar.success("Loaded last saved run.")
else:
    st.sidebar.caption("No saved run yet — run a batch to create one.")

st.sidebar.markdown("---")
st.sidebar.write(f"Total transactions in dataset: {TOTAL_TXNS}")
st.sidebar.write(df["failure_stage"].value_counts())

# --- Session state to persist results across reruns ---
if "results" not in st.session_state:
    st.session_state.results = []

# --- Run batch, live, from the UI ---
if run_button:
    recovery_app = build_graph()
    batch = df.head(batch_size).to_dict(orient="records")

    st.session_state.results = []
    progress = st.progress(0, text="Starting batch...")
    status_line = st.empty()

    for i, txn in enumerate(batch):
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
        final_state = recovery_app.invoke(initial_state, config={"recursion_limit": 50})
        st.session_state.results.append(final_state)
        progress.progress(
            (i + 1) / len(batch),
            text=f"Processed {i + 1}/{len(batch)} — {txn['txn_id']}",
        )

    progress.empty()

    # Auto-save so this run can be reloaded instantly later without re-running
    os.makedirs("results", exist_ok=True)
    with open(SAVED_RESULTS_PATH, "w") as f:
        json.dump(st.session_state.results, f, indent=2, default=str)
    metrics_snapshot = compute_metrics(st.session_state.results)
    with open("results/batch_metrics.json", "w") as f:
        json.dump(metrics_snapshot, f, indent=2)
    status_line.success(f"Batch complete — results saved to {SAVED_RESULTS_PATH}")

# --- Display results ---
results = st.session_state.results

if not results:
    st.info("Set a batch size in the sidebar and click **Run Recovery Batch** to start — or **Load Last Saved Run** if one exists.")
else:
    m = compute_metrics(results)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total At-Risk", f"₹{m['total_at_risk_amount']:,.0f}")
    col2.metric("Recovered", f"₹{m['total_recovered_amount']:,.0f}")
    col3.metric("Recovery Rate", f"{m['recovery_rate_pct']}%")
    col4.metric("Escalations", m["escalations_count"])
    col5.metric("Stopped by Rule", m["stopped_count"])

    st.markdown("---")
    st.subheader("Breakdown")

    bcol1, bcol2, bcol3 = st.columns(3)

    with bcol1:
        st.markdown("**Decisions taken**")
        st.dataframe(
            pd.DataFrame(
                list(m["decisions_breakdown"].items()),
                columns=["Decision", "Count"],
            ),
            use_container_width=True,
            hide_index=True,
        )

    with bcol2:
        st.markdown("**Success rate by decision**")
        st.dataframe(
            pd.DataFrame(
                list(m["success_rate_by_decision_pct"].items()),
                columns=["Decision", "Success %"],
            ),
            use_container_width=True,
            hide_index=True,
        )

    with bcol3:
        st.markdown("**Stopped — by reason**")
        if m["stopped_by_reason"]:
            st.dataframe(
                pd.DataFrame(
                    list(m["stopped_by_reason"].items()),
                    columns=["Reason", "Count"],
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("None stopped in this batch.")

    st.markdown("**Recovered ₹ by failure stage**")
    stage_df = pd.DataFrame(
        {
            "At-Risk": m["at_risk_by_stage"],
            "Recovered": m["recovered_by_stage"],
        }
    ).fillna(0)
    st.bar_chart(stage_df)

    st.markdown("---")
    st.subheader("Transaction Trace")

    for r in results:
        txn = r["txn"]
        stop_reason = r.get("stop_reason")
        header = f"{txn['txn_id']} — {txn['failure_code']} — ₹{txn['amount']:.0f}"
        if stop_reason:
            header += "  🛑 HALTED"

        with st.expander(header):
            st.write(f"**Stage:** {txn['failure_stage']}")
            st.write(f"**Payment method:** {txn['payment_method']}")
            st.write(f"**Segment:** {txn.get('customer_segment', 'regular')}")

            if stop_reason:
                st.error(f"Stopped — reason: {stop_reason}")
            else:
                st.markdown("**Diagnosis**")
                st.write(r["diagnosis"])

                st.markdown("**Decision**")
                st.write(f"`{r['decision']}` — {r['decision_reasoning']}")

                st.markdown("**Action Result**")
                st.json(r["action_result"])

    st.markdown("---")
    st.subheader("Audit Log (final summary per transaction)")
    audit_rows = []
    for r in results:
        log = r.get("audit_log", [])
        final_entries = [e for e in log if e.get("entry_type") == "final_summary"]
        audit_rows.append(final_entries[-1] if final_entries else (log[-1] if log else {}))
    st.dataframe(pd.DataFrame(audit_rows), use_container_width=True)

    with st.expander("Full audit log — every attempt, all transactions"):
        all_entries = [e for r in results for e in r.get("audit_log", [])]
        st.dataframe(pd.DataFrame(all_entries), use_container_width=True)