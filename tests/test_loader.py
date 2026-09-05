"""CSV loader: data/loader.py"""

import pytest

from data.loader import load_transactions


def test_loads_the_real_dataset():
    df, report = load_transactions("data/failed_transactions.csv")
    assert report["rows_out"] == len(df) == 500
    assert df["do_not_contact"].dtype == bool
    assert str(df["amount"].dtype).startswith("float")


def test_missing_required_column_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("txn_id,amount\nt1,100\n")
    with pytest.raises(ValueError):
        load_transactions(str(p))


def test_bad_amount_rows_dropped(tmp_path):
    p = tmp_path / "amt.csv"
    p.write_text(
        "txn_id,amount,payment_method,failure_code,failure_stage,retry_count,do_not_contact\n"
        "t1,100,card,insufficient_funds,payment_failure,0,False\n"
        "t2,-5,card,insufficient_funds,payment_failure,0,False\n"
        "t3,,card,insufficient_funds,payment_failure,0,False\n"
    )
    df, report = load_transactions(str(p))
    assert report["dropped_bad_amount"] == 2
    assert list(df["txn_id"]) == ["t1"]


def test_do_not_contact_normalisation(tmp_path):
    p = tmp_path / "dnc.csv"
    p.write_text(
        "txn_id,amount,payment_method,failure_code,failure_stage,retry_count,do_not_contact\n"
        "t1,100,card,insufficient_funds,payment_failure,0,TRUE\n"
        "t2,100,card,insufficient_funds,payment_failure,0,no\n"
    )
    df, _ = load_transactions(str(p))
    assert list(df["do_not_contact"]) == [True, False]
