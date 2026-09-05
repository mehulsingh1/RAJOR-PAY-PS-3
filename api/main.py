"""
FastAPI backend for the Revenue Recovery Operations Center.

    uvicorn api.main:app --reload
"""

import csv
import io
import sys

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.events import BUS
from api.worker import SERVICE
from data.live_store import COLUMNS
from learning.priors import PRIORS

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

app = FastAPI(title="Revenue Recovery Ops Center")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class StartReq(BaseModel):
    rate: float = 1.0
    seed: int = 7


@app.get("/health")
def health():
    return {"ok": True, "running": SERVICE.running}


@app.post("/simulation/start")
async def sim_start(req: StartReq):
    await SERVICE.start(req.rate, req.seed)
    return {"running": True, "rate": SERVICE.rate}


@app.post("/simulation/stop")
async def sim_stop():
    await SERVICE.stop()
    return {"running": False}


@app.post("/simulation/reset")
async def sim_reset():
    await SERVICE.stop()
    SERVICE.reset()
    return {"ok": True}


@app.get("/transactions")
def transactions(status: str | None = Query(None), limit: int = 500):
    rows = SERVICE.store.all()
    if status:
        rows = [r for r in rows if r.get("status", "").startswith(status)]
    rows = sorted(rows, key=lambda r: r.get("updated_at", ""), reverse=True)
    return {"count": len(rows), "transactions": rows[:limit]}


@app.get("/transactions/{txn_id}")
def transaction(txn_id: str):
    row = SERVICE.store.get(txn_id)
    if not row:
        return {"error": "not found"}
    return {"transaction": row, "notifications": SERVICE.outbox.for_txn(txn_id)}


@app.get("/metrics")
def metrics():
    return SERVICE.metrics()


@app.get("/notifications")
def notifications(limit: int = 200):
    recs = list(reversed(SERVICE.outbox.all()))[:limit]
    return {"count": len(recs), "notifications": recs}


@app.get("/queue")
def queue():
    return {"count": len(SERVICE.queue),
            "items": [v["row"] for v in SERVICE.queue.values()]}


class QueueAction(BaseModel):
    action: str            # approve | override | reject
    override: str | None = None


@app.post("/queue/{txn_id}")
def queue_resolve(txn_id: str, body: QueueAction):
    return SERVICE.resolve_queue(txn_id, body.action, body.override)


@app.get("/learning")
def learning():
    return {"priors": PRIORS.snapshot()}


@app.get("/stream")
async def stream():
    return EventSourceResponse(BUS.subscribe())


def _csv_response(rows: list[dict], fieldnames: list[str], name: str):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


@app.get("/export/transactions.csv")
def export_txns():
    return _csv_response(SERVICE.store.all(), COLUMNS, "transactions.csv")


@app.get("/export/notifications.csv")
def export_notifs():
    recs = SERVICE.outbox.all()
    fields = list(recs[0].keys()) if recs else ["notif_id"]
    return _csv_response(recs, fields, "notifications.csv")
