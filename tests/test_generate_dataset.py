"""Dataset generator: data/generate_dataset.py"""

from collections import Counter

from data.generate_dataset import generate, CODE_STAGE
from data.loader import load_transactions, REQUIRED_COLUMNS


def test_deterministic():
    assert generate(120, seed=1) == generate(120, seed=1)


def test_row_count_and_columns():
    rows = generate(200)
    assert len(rows) == 200
    assert REQUIRED_COLUMNS <= set(rows[0])


def test_stage_matches_code():
    for r in generate(200):
        assert r["failure_stage"] == CODE_STAGE[r["failure_code"]]


def test_days_overdue_only_for_invoices():
    for r in generate(200):
        if r["failure_code"] == "invoice_unpaid":
            assert r["days_overdue"] != ""
        else:
            assert r["days_overdue"] == ""


def test_distributions_in_sane_bands():
    rows = generate(400)
    n = len(rows)
    seg = Counter(r["customer_segment"] for r in rows)
    assert 0.10 < seg["high_value"] / n < 0.28
    dnc = sum(bool(r["do_not_contact"]) for r in rows) / n
    assert 0.02 < dnc < 0.14
    codes = Counter(r["failure_code"] for r in rows)
    assert len(codes) == 9  # every failure code represented


def test_written_csv_loads_clean(tmp_path):
    from data.generate_dataset import write_csv
    p = tmp_path / "gen.csv"
    write_csv(generate(50), str(p))
    df, report = load_transactions(str(p))
    assert report["dropped_bad_amount"] == 0 and len(df) == 50
