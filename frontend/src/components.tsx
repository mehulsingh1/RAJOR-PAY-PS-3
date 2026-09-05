import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { API, Evt, get, inr, post, usePoll } from "./api";

export const BgFx = () => <div className="bg-fx" />;

const statusClass = (s: string) => (s || "").split(":")[0];

/* ---------------- Header + simulation controls ---------------- */
export function Header({ connected }: { connected: boolean }) {
  const health = usePoll<any>("/health", 2000);
  const [rate, setRate] = useState(1.5);
  const running = !!health?.running;
  return (
    <header className="top">
      <h1>Revenue Recovery <span style={{ color: "var(--accent)" }}>Ops Center</span></h1>
      <span className="tag">payment failures → AI recovery → money back · <em>simulation</em></span>
      <span className="spacer" />
      <span className="mini">
        <span className={"dot " + (connected ? "on" : "off")} />{" "}
        {connected ? "live" : "offline"}
      </span>
      <span className="mini">rate {rate.toFixed(1)}/s</span>
      <input
        className="range" type="range" min={0.3} max={6} step={0.1}
        value={rate} onChange={(e) => setRate(+e.target.value)}
      />
      {running ? (
        <button className="btn" onClick={() => post("/simulation/stop")}>Pause</button>
      ) : (
        <button className="btn primary" onClick={() => post("/simulation/start", { rate })}>
          Start simulation
        </button>
      )}
      <button className="btn ghost" onClick={() => post("/simulation/reset")}>Reset</button>
    </header>
  );
}

/* ---------------- Metric tiles ---------------- */
export function MetricsRow() {
  const m = usePoll<any>("/metrics", 1500);
  const met = m?.metrics;
  const cmp = m?.comparison?.by_strategy?.agent;
  const sim = m?.sim || {};
  const tiles = [
    { k: "Payments seen", v: (sim.attempts ?? 0).toLocaleString(), sub: `${sim.failures ?? 0} failed` },
    { k: "At-risk", v: inr(met?.total_at_risk_amount ?? 0) },
    { k: "Net recovered", v: inr(met?.net_recovered_amount ?? 0), good: true,
      sub: met ? `gross ${inr(met.total_recovered_amount)} − cost ${inr(met.total_intervention_cost)}` : "" },
    { k: "Net recovery rate", v: (met?.net_recovery_rate_pct ?? 0) + "%" },
    { k: "Escalations", v: met?.escalations_count ?? 0, sub: `${m?.queue_size ?? 0} awaiting human` },
    { k: "Compliance stops", v: (met?.stopped_count ?? 0) + " / " + (met?.compliance_overrides_count ?? 0),
      sub: "halted / overridden" },
  ];
  return (
    <div className="tiles">
      {tiles.map((t) => (
        <motion.div key={t.k} layout className="card tile">
          <div className="k">{t.k}</div>
          <div className={"v" + (t.good ? " good" : "")}>{t.v}</div>
          {t.sub ? <div className="sub">{t.sub}</div> : null}
        </motion.div>
      ))}
    </div>
  );
}

/* ---------------- Live transaction feed ---------------- */
export function LiveFeed({ events }: { events: Evt[] }) {
  const txns = usePoll<any>("/transactions?limit=60", 1500);
  const rows = txns?.transactions ?? [];
  return (
    <div className="card">
      <h2>Live transaction feed</h2>
      <div className="feed">
        <AnimatePresence initial={false}>
          {rows.map((r: any) => (
            <motion.div
              key={r.txn_id} layout
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }} className="row"
            >
              <span className={"chip " + statusClass(r.status)}>{r.status}</span>
              <span className="mono">{r.txn_id.slice(0, 12)}</span>
              <span>{r.failure_code}</span>
              {r.decision ? <span className="mini">→ {r.decision}</span> : null}
              <span className="amt">{inr(+r.amount)}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        {rows.length === 0 && <div className="mini">Start the simulation to see payments fail and recover.</div>}
      </div>
    </div>
  );
}

/* ---------------- Agent activity timeline ---------------- */
const LABEL: Record<string, (d: any) => string> = {
  payment_failed: (d) => `payment failed — ${d.failure_code} ${inr(d.amount)} (risk ${d.risk_score})`,
  agent_step: (d) => `agent ${d.step} ${d.txn_id.slice(0, 10)}`,
  notification: (d) => `sent ${d.channel}/${d.lang} — "${(d.body || "").slice(0, 60)}…"`,
  compliance: (d) => `compliance: ${d.note}`,
  escalation: (d) => `escalated ${d.txn_id.slice(0, 10)} ${inr(d.amount)} → human queue`,
  resolved: (d) => `${d.status} ${d.txn_id.slice(0, 10)} — net ${inr(d.net)}`,
  queue_resolved: (d) => `human ${d.action} ${d.txn_id.slice(0, 10)}${d.chosen ? " → " + d.chosen : ""}`,
};
export function AgentTimeline({ events }: { events: Evt[] }) {
  const shown = events.filter((e) => LABEL[e.kind]).slice(0, 40);
  return (
    <div className="card">
      <h2>Agent activity</h2>
      <div className="feed timeline">
        <AnimatePresence initial={false}>
          {shown.map((e, i) => (
            <motion.div key={e.ts + i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="ev">
              <div className="t">{e.ts.slice(11, 19)}</div>
              <div className="m">{LABEL[e.kind](e.data)}</div>
            </motion.div>
          ))}
        </AnimatePresence>
        {shown.length === 0 && <div className="mini">No activity yet.</div>}
      </div>
    </div>
  );
}

/* ---------------- Recovery funnel ---------------- */
export function Funnel() {
  const m = usePoll<any>("/metrics", 2000);
  const c = m?.status_counts || {};
  const grp = (pfx: string) =>
    Object.entries(c).filter(([k]) => k.startsWith(pfx)).reduce((a, [, v]) => a + (v as number), 0);
  const stages = [
    ["Failed", grp("failed") + grp("queued") + grp("diagnosing") + grp("acting")],
    ["In progress", grp("queued") + grp("diagnosing") + grp("acting")],
    ["Recovered", grp("recovered")],
    ["Escalated", grp("escalated")],
    ["Lost / halted", grp("lost") + grp("halted")],
  ] as [string, number][];
  const max = Math.max(1, ...stages.map(([, v]) => v));
  return (
    <div className="card">
      <h2>Recovery funnel</h2>
      {stages.map(([label, v]) => (
        <div key={label} style={{ margin: "10px 0" }}>
          <div className="mini" style={{ display: "flex", justifyContent: "space-between" }}>
            <span>{label}</span><span>{v}</span>
          </div>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

/* ---------------- Baseline comparison ---------------- */
const NAMES: Record<string, string> = {
  agent: "AI agent", retry_all: "Retry everything",
  reminder_all: "Always remind", static_playbook: "Static playbook",
};
export function BaselineCompare() {
  const m = usePoll<any>("/metrics", 2500);
  const by = m?.comparison?.by_strategy;
  const up = m?.comparison?.agent_uplift_over_best_baseline;
  const data = by
    ? Object.entries(by).map(([k, v]: any) => ({
        name: NAMES[k] ?? k, Gross: v.recovered, Net: v.net_recovered,
      }))
    : [];
  return (
    <div className="card">
      <h2>Agent vs non-AI baselines — net of intervention cost</h2>
      <div style={{ height: 240 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="name" tick={{ fill: "#97a1c4", fontSize: 11 }} />
            <YAxis tick={{ fill: "#97a1c4", fontSize: 11 }} width={70}
              tickFormatter={(v) => "₹" + (v / 1000).toFixed(0) + "k"} />
            <Tooltip formatter={(v: any) => inr(v)} contentStyle={{ background: "#0b1020", border: "1px solid #2a3358" }} />
            <Bar dataKey="Gross" fill="#3a4a7e" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Net" radius={[4, 4, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.name === "AI agent" ? "#3ddc97" : "#6ea8fe"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {up && (
        <div className="mini" style={{ marginTop: 8 }}>
          {up.extra_net_recovered >= 0
            ? `Agent nets ${inr(up.extra_net_recovered)} more than the best baseline (${NAMES[up.vs] ?? up.vs}) — +${up.extra_net_rate_pp} pp. Gross delta ${inr(up.extra_gross_recovered)}.`
            : `Agent is ${inr(-up.extra_net_recovered)} behind the best baseline (${NAMES[up.vs] ?? up.vs}) on net for this batch.`}
        </div>
      )}
    </div>
  );
}

/* ---------------- Learning panel ---------------- */
export function LearningPanel() {
  const d = usePoll<any>("/learning", 2500);
  const rows = (d?.priors ?? []).filter((p: any) => p.total >= 3).slice(0, 12);
  return (
    <div className="card">
      <h2>Learning loop — observed success by (failure, action)</h2>
      <div className="scroll" style={{ maxHeight: 260 }}>
        <table className="data">
          <thead><tr><th>failure</th><th>action</th><th>obs</th><th>rate</th><th /></tr></thead>
          <tbody>
            {rows.map((p: any, i: number) => (
              <tr key={i}>
                <td>{p.failure_code}</td>
                <td>{p.action}</td>
                <td>{p.successes}/{p.total}</td>
                <td style={{ color: p.active ? "var(--good)" : "var(--ink-dim)" }}>
                  {(p.observed_rate * 100).toFixed(0)}%
                </td>
                <td className="mini">{p.active ? "blending" : "warming"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="mini">No outcomes recorded yet.</div>}
      </div>
    </div>
  );
}

/* ---------------- Human-in-the-loop queue ---------------- */
const ACTIONS = ["retry", "send_reminder", "apply_discount", "escalate_human", "request_mandate_renewal"];
export function QueuePanel() {
  const q = usePoll<any>("/queue", 1500);
  const items = q?.items ?? [];
  const [busy, setBusy] = useState<string | null>(null);
  const act = async (id: string, action: string, override?: string) => {
    setBusy(id);
    await post(`/queue/${id}`, { action, override });
    setBusy(null);
  };
  return (
    <div className="card">
      <h2>Human-in-the-loop queue ({items.length})</h2>
      <div className="feed">
        {items.map((r: any) => (
          <div key={r.txn_id} className="msg">
            <div className="meta">
              <span className="mono">{r.txn_id.slice(0, 12)}</span>
              <span>{r.failure_code}</span>
              <span>{inr(+r.amount)}</span>
              <span>{r.customer_segment}</span>
            </div>
            <div style={{ fontSize: 12.5, margin: "4px 0" }}>{r.diagnosis}</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
              <button className="btn primary" disabled={busy === r.txn_id}
                onClick={() => act(r.txn_id, "approve")}>Approve escalation</button>
              <select className="btn ghost" defaultValue=""
                onChange={(e) => e.target.value && act(r.txn_id, "override", e.target.value)}>
                <option value="">Override…</option>
                {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
              <button className="btn ghost" disabled={busy === r.txn_id}
                onClick={() => act(r.txn_id, "reject")}>Reject</button>
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="mini">Nothing waiting on a human.</div>}
      </div>
    </div>
  );
}

/* ---------------- Notification center ---------------- */
export function NotificationCenter() {
  const d = usePoll<any>("/notifications?limit=40", 1500);
  const recs = d?.notifications ?? [];
  const [ch, setCh] = useState("all");
  const filtered = recs.filter((r: any) => ch === "all" || r.channel === ch);
  return (
    <div className="card">
      <h2>Notification center — simulated outbox</h2>
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        {["all", "email", "sms", "whatsapp"].map((c) => (
          <button key={c} className={"btn ghost" + (ch === c ? " primary" : "")}
            onClick={() => setCh(c)}>{c}</button>
        ))}
      </div>
      <div className="feed">
        {filtered.map((r: any) => (
          <div key={r.notif_id} className="msg">
            <div className="meta">
              <span>{r.channel}</span>
              <span className={r.lang === "hinglish" ? "lang-hinglish" : ""}>{r.lang}</span>
              <span className="mono">{r.txn_id.slice(0, 10)}</span>
              <span>·  ₹{r.cost}</span>
              <span>{r.simulated === "True" || r.simulated === true ? "simulated" : "sent"}</span>
            </div>
            {r.subject ? <div style={{ fontWeight: 600, marginBottom: 2 }}>{r.subject}</div> : null}
            <div>{r.body}</div>
          </div>
        ))}
        {filtered.length === 0 && <div className="mini">No messages yet.</div>}
      </div>
    </div>
  );
}

/* ---------------- Data explorer ---------------- */
const COLS = ["txn_id", "status", "failure_code", "amount", "customer_segment",
  "decision", "gross_recovered", "net_recovered", "notifications_sent", "ptp_date", "risk_score"];
export function DataExplorer() {
  const d = usePoll<any>("/transactions?limit=500", 2500);
  const rows: any[] = d?.transactions ?? [];
  const [sort, setSort] = useState<{ k: string; dir: 1 | -1 }>({ k: "risk_score", dir: -1 });
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState<any>(null);
  const view = useMemo(() => {
    let v = rows.filter((r) => !q || JSON.stringify(r).toLowerCase().includes(q.toLowerCase()));
    v = [...v].sort((a, b) => {
      const x = a[sort.k], y = b[sort.k];
      const nx = parseFloat(x), ny = parseFloat(y);
      const cmp = !isNaN(nx) && !isNaN(ny) ? nx - ny : String(x).localeCompare(String(y));
      return cmp * sort.dir;
    });
    return v;
  }, [rows, q, sort]);
  return (
    <div className="card">
      <h2>Data explorer — the live CSV</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input className="btn ghost" placeholder="filter…" value={q}
          onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
        <a className="btn" href={API + "/export/transactions.csv"}>Download transactions</a>
        <a className="btn" href={API + "/export/notifications.csv"}>Download notifications</a>
      </div>
      <div className="scroll">
        <table className="data">
          <thead>
            <tr>{COLS.map((c) => (
              <th key={c} onClick={() => setSort((s) => ({ k: c, dir: s.k === c && s.dir === -1 ? 1 : -1 }))}>
                {c}{sort.k === c ? (sort.dir === -1 ? " ▾" : " ▴") : ""}
              </th>
            ))}</tr>
          </thead>
          <tbody>
            {view.map((r) => (
              <tr key={r.txn_id} onClick={() => get(`/transactions/${r.txn_id}`).then(setDetail)}>
                {COLS.map((c) => (
                  <td key={c}>
                    {c === "status" ? <span className={"chip " + (r.status || "").split(":")[0]}>{r.status}</span>
                      : c === "amount" || c.includes("recovered") ? inr(+r[c] || 0)
                      : String(r[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail && (
        <div className="msg" style={{ marginTop: 10 }}>
          <div className="meta">
            <strong>{detail.transaction?.txn_id}</strong>
            <button className="btn ghost" onClick={() => setDetail(null)}>close</button>
          </div>
          <div>diagnosis: {detail.transaction?.diagnosis || "—"}</div>
          <div>decision: {detail.transaction?.decision} · flags: {detail.transaction?.compliance_flags || "none"}</div>
          <div>PTP: {detail.transaction?.ptp_date || "—"} ({detail.transaction?.ptp_status || "n/a"})</div>
          <div style={{ marginTop: 6 }}>{(detail.notifications ?? []).length} message(s):</div>
          {(detail.notifications ?? []).map((n: any) => (
            <div key={n.notif_id} className="mini">· {n.channel}/{n.lang}: {n.body}</div>
          ))}
        </div>
      )}
    </div>
  );
}
