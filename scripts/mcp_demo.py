"""
Proof that the recovery actions run over a real MCP server.

Starts mcp_server.server as a subprocess, lists the tools it advertises over the
protocol, and calls a couple of them.

    python -m scripts.mcp_demo
"""

from mcp_tools.client import get_client

SAMPLE_TXNS = [
    {
        "txn_id": "txn_demo_card", "amount": 2499.0, "payment_method": "card",
        "failure_code": "card_expired", "failure_stage": "payment_failure",
        "retry_count": 0, "customer_segment": "regular",
    },
    {
        "txn_id": "txn_demo_invoice", "amount": 42000.0, "payment_method": "netbanking",
        "failure_code": "invoice_unpaid", "failure_stage": "receivable_overdue",
        "retry_count": 0, "customer_segment": "high_value", "days_overdue": 61,
    },
]


def main():
    client = get_client()

    print("Tools advertised by the MCP server:")
    for name in client.list_tools():
        print(f"  - {name}")

    print("\nCalling tools over MCP:")
    for txn in SAMPLE_TXNS:
        res = client.call("send_reminder", txn)
        print(f"  send_reminder({txn['txn_id']}) -> {res}")

    client.close()


if __name__ == "__main__":
    main()
