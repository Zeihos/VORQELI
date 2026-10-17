import json
from vorqeli_connect.history import load_history, record_scan, MAX_RECORDS


def test_history_roundtrip(tmp_path):
    path = tmp_path / "history.json"
    record_scan([("Discord", "Доступен")], path)
    assert load_history(path)[0]["results"] == {"Discord": "Доступен"}


def test_corrupt_history(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("not json")
    assert load_history(path) == []


def test_bounded_history(tmp_path):
    path = tmp_path / "history.json"
    for i in range(MAX_RECORDS + 3):
        record_scan([("test", str(i))], path)
    assert len(load_history(path)) == MAX_RECORDS
    assert load_history(path)[-1]["results"]["test"] == str(MAX_RECORDS + 2)
