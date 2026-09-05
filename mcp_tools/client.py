"""
Synchronous client for the Razorpay Recovery MCP server.

LangGraph nodes are synchronous, so this wraps the async MCP stdio client in a
dedicated background event-loop thread and exposes plain blocking methods.

A single worker coroutine owns the stdio session for its whole lifetime and
services requests from a queue — so every async context-manager enter/exit
happens in the same task (anyio requires this). One server subprocess is started
on first use and reused for the whole batch.

Enable it with USE_MCP=1 (see graph/nodes.act_node).
"""

import asyncio
import json
import sys
import threading
from concurrent.futures import Future
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mcp_server.server"],
)
_STOP = object()


class MCPRecoveryClient:
    """Blocking facade over an MCP stdio session running on a background loop."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        make_q: Future = Future()
        self._loop.call_soon_threadsafe(
            lambda: make_q.set_result(asyncio.Queue())
        )
        self._queue: "asyncio.Queue" = make_q.result(timeout=10)

        started: Future = Future()
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self._worker(started))
        )
        started.result(timeout=30)  # raises if the server failed to start

    async def _worker(self, started: Future):
        """Owns the session for its whole lifetime; services queued requests."""
        try:
            async with stdio_client(_SERVER) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    started.set_result(True)
                    while True:
                        kind, payload, fut = await self._queue.get()
                        if kind is _STOP:
                            return
                        try:
                            if kind == "__list__":
                                res = await session.list_tools()
                                fut.set_result([t.name for t in res.tools])
                            else:
                                res = await session.call_tool(kind, {"txn": payload})
                                fut.set_result(_parse_result(kind, res))
                        except Exception as e:  # noqa: BLE001
                            fut.set_exception(e)
        except Exception as e:  # noqa: BLE001
            if not started.done():
                started.set_exception(e)

    def _submit(self, kind, payload) -> dict:
        fut: Future = Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (kind, payload, fut))
        return fut.result(timeout=30)

    def list_tools(self) -> list[str]:
        return self._submit("__list__", None)

    def call(self, action: str, txn: dict) -> dict:
        return self._submit(action, txn)

    def close(self):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (_STOP, None, None))
        self._loop.call_soon_threadsafe(self._loop.stop)


def _parse_result(action: str, res) -> dict:
    if getattr(res, "structuredContent", None):
        sc = res.structuredContent
        return sc.get("result", sc)
    for block in getattr(res, "content", []):
        if getattr(block, "type", None) == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                pass
    return {
        "action": action, "success": False, "amount_recovered": 0.0,
        "message": "MCP call returned no parseable result",
    }


_client: Optional[MCPRecoveryClient] = None


def get_client() -> MCPRecoveryClient:
    global _client
    if _client is None:
        _client = MCPRecoveryClient()
    return _client
