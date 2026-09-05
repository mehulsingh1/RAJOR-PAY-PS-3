"""
Transaction CSV loader with schema validation and type coercion.

Both entry points (app.py, run_batch.py) load through here so a malformed row
fails loudly at the edge instead of blowing up mid-batch inside a graph node.
"""

import pandas as pd

REQUIRED_COLUMNS = {
    "txn_id",
    "amount",
    "payment_method",
    "failure_code",
    "failure_stage",
    "retry_count",
    "do_not_contact",
}

_TRUTHY = {"true", "1", "yes", "y", "t"}


def load_transactions(path: str) -> tuple[pd.DataFrame, dict]:
    """
    Load and validate the transaction CSV.

    Returns (clean_dataframe, report) where report describes what was cleaned:
        {"rows_in": int, "rows_out": int, "dropped_bad_amount": int}
    Raises ValueError if required columns are missing.
    """
    df = pd.read_csv(path)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {sorted(missing)}"
        )

    rows_in = len(df)

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["retry_count"] = (
        pd.to_numeric(df["retry_count"], errors="coerce").fillna(0).astype(int)
    )

    bad_amount = df["amount"].isna() | (df["amount"] <= 0)
    dropped = int(bad_amount.sum())
    df = df[~bad_amount].reset_index(drop=True)

    # Normalise do_not_contact to a real bool regardless of how it was stored.
    df["do_not_contact"] = (
        df["do_not_contact"].astype(str).str.strip().str.lower().isin(_TRUTHY)
    )

    if "days_overdue" in df.columns:
        df["days_overdue"] = pd.to_numeric(df["days_overdue"], errors="coerce")

    report = {
        "rows_in": rows_in,
        "rows_out": len(df),
        "dropped_bad_amount": dropped,
    }
    return df, report
