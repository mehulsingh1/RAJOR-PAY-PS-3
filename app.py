"""
Streamlit UI for the AI Revenue Recovery agent.
Runs the LangGraph pipeline on a batch of transactions and shows
live input/output per transaction: diagnosis, decision, action, stop reason.
"""

import streamlit as st
import pandas as pd

from graph.build_graph import build_graph

st.set_page_config(page_title="AI Revenue Recovery Agent", layout="wide")

st.title("AI Revenue Recovery Agent")
st.caption("Razorpay Buildathon — Detect → Diagnose → Decide → Act → Log")

# --- Load data ---
DATA_PATH = "data/failed_transactions.csv"

@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)

df = load_data()

# --- Sidebar controls ---
st.sidebar.header("Batch Controls")
batch_size = st.sidebar.slider("Number of transactions to process", 1, 30, 5)
run_button = st.sidebar.button("Run Recovery Batch", type="primary")

st.sidebar.markdown("---")
st.sidebar.write(f"Total transactions in dataset: {len(df)}")
st.sidebar.write(df["failure_stage"].value_counts())

# --- Session state to persist results across reruns ---
if "results" not in st.session_state:
    st.session_state.results = []

# --- Run batch ---
if run_button:
    app = build_graph()
    batch = df.head(batch_size).to_dict(orient="records")

    st.session_state.results = []
    progress = st.progress(0, text="Starting batch...")

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
        final_state = app.invoke(initial_state)
        st.session_state.results.append(final_state)
        progress.progress(
            (i + 1) / len(batch),
            text=f"Processed {i + 1}/{len(batch)} — {txn['txn_id']}",
        )

    progress.empty()

# --- Display results ---
results = st.session_state.results

if not results:
    st.info("Set a batch size and click **Run Recovery Batch** to start.")
else:
    # Summary metrics
    total_at_risk = sum(r["txn"]["amount"] for r in results)
    recovered = sum(
        r["action_result"].get("amount_recovered", 0)
        for r in results
        if r["action_result"].get("success")
    )
    escalations = sum(1 for r in results if r["decision"] == "escalate_human")
    stopped = sum(1 for r in results if r.get("stop_reason"))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total At-Risk", f"₹{total_at_risk:,.0f}")
    col2.metric("Recovered (sim)", f"₹{recovered:,.0f}")
    col3.metric("Escalations", escalations)
    col4.metric("Stopped by Rule", stopped)

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
    st.subheader("Audit Log (raw)")
    audit_rows = [r["audit_log"][0] for r in results if r.get("audit_log")]
    st.dataframe(pd.DataFrame(audit_rows), use_container_width=True)