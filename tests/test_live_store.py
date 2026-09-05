"""LiveStore: data/live_store.py"""

from data.live_store import LiveStore, COLUMNS
from tests.conftest import txn


def test_append_and_read(tmp_path):
    s = LiveStore(path=str(tmp_path / "live.csv"))
    row = s.append_failure(txn(txn_id="t1"))
    assert row["status"] == "failed" and set(row) == set(COLUMNS)
    assert s.get("t1")["txn_id"] == "t1"
    assert len(s.pending()) == 1


def test_update_status(tmp_path):
    s = LiveStore(path=str(tmp_path / "live.csv"))
    s.append_failure(txn(txn_id="t1"))
    s.update("t1", status="recovered", net_recovered=900)
    assert s.get("t1")["status"] == "recovered"
    assert s.pending() == []


def test_persists_across_instances(tmp_path):
    p = str(tmp_path / "live.csv")
    LiveStore(path=p).append_failure(txn(txn_id="t1"))
    assert LiveStore(path=p).get("t1") is not None


def test_reset(tmp_path):
    s = LiveStore(path=str(tmp_path / "live.csv"))
    s.append_failure(txn(txn_id="t1"))
    s.reset()
    assert s.all() == []
