"""Person 2: hash-chained audit log."""
import json

from workflow.audit import GENESIS, AuditLog


def make_log(tmp_path, n=3):
    log = AuditLog(tmp_path / "audit.json")
    for i in range(n):
        log.record(actor=f"user{i}", role="developer", action="test", model_id="LR-R-001", details={"i": i})
    return log


def test_events_are_chained(tmp_path):
    events = make_log(tmp_path).events()
    assert events[0].prev_hash == GENESIS
    assert [e.prev_hash for e in events[1:]] == [e.hash for e in events[:-1]]
    assert make_log(tmp_path / "other").verify() == []


def test_edited_event_is_detected(tmp_path):
    log = make_log(tmp_path)
    data = json.loads(log._store.path.read_text())
    data[1]["details"]["i"] = 99
    log._store.path.write_text(json.dumps(data))
    problems = log.verify()
    assert len(problems) == 1 and "edited" in problems[0]


def test_deleted_event_is_detected(tmp_path):
    log = make_log(tmp_path)
    data = json.loads(log._store.path.read_text())
    del data[1]
    log._store.path.write_text(json.dumps(data))
    assert any("removed or reordered" in p for p in log.verify())


def test_missing_log_is_empty(tmp_path):
    log = AuditLog(tmp_path / "none.json")
    assert log.events() == [] and log.verify() == []
