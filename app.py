"""
Streamlit UI for the AI Revenue Recovery agent.
Runs the LangGraph pipeline on a batch of transactions and shows
live input/output per transaction: diagnosis, decision, action, stop reason.
"""

import streamlit as st
import pandas as pd

from graph.build_graph import build_graph
from metrics.engine import compute_metrics

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
    st.subheader("Audit Log (raw)")
    audit_rows = [r["audit_log"][0] for r in results if r.get("audit_log")]
    st.dataframe(pd.DataFrame(audit_rows), use_container_width=True)