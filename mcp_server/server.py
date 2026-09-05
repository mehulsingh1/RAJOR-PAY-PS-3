"""
Razorpay Recovery MCP server.

Exposes the five recovery actions as real Model Context Protocol tools over stdio.
The Act node talks to this server through mcp_tools/client.py; the outcome logic
itself still lives in mcp_tools/tools.py, so the server is a thin protocol wrapper.

Run standalone:
    python -m mcp_server.server
"""

from mcp.server.fastmcp import FastMCP

from mcp_tools.tools import (
    retry_payment,
    send_reminder as _send_reminder,
    apply_discount as _apply_discount,
    escalate_human as _escalate_human,
    request_mandate_renewal as _request_mandate_renewal,
)

mcp = FastMCP("razorpay-recovery")


@mcp.tool()
def retry(txn: dict) -> dict:
    """Retry the failed payment on its original instrument (respects retry caps)."""
    return retry_payment(txn)


@mcp.tool()
def send_reminder(txn: dict) -> dict:
    """Send the customer a payment / checkout-recovery reminder."""
    return _send_reminder(txn)


@mcp.tool()
def apply_discount(txn: dict) -> dict:
    """Offer a small discount to win back an abandoned or hesitant payment."""
    return _apply_discount(txn)


@mcp.tool()
def escalate_human(txn: dict) -> dict:
    """Hand the transaction to a human collections agent."""
    return _escalate_human(txn)


@mcp.tool()
def request_mandate_renewal(txn: dict) -> dict:
    """Send an e-mandate / NACH re-authorization link for a lapsed mandate."""
    return _request_mandate_renewal(txn)


if __name__ == "__main__":
    mcp.run()
