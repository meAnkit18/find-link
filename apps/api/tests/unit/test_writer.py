import pytest

from graph_core.exceptions import QueryExecutionError

from graph_explorer_api.ingest import writer
from tests.unit.fakes import FakeGraphClient


def test_coerce_value_int_and_float_and_bool_and_empty():
    assert writer.coerce_value("42", "int") == (42, True)
    assert writer.coerce_value("3.5", "float") == (3.5, True)
    assert writer.coerce_value("true", "bool") == (True, True)
    assert writer.coerce_value("", "int") == (None, True)


def test_coerce_value_reports_failure_without_raising():
    value, ok = writer.coerce_value("not-a-number", "int")
    assert value is None
    assert ok is False


def test_write_vertices_dedupes_and_batches():
    client = FakeGraphClient()
    rows = [("v1", {"label": "Alice"}), ("v2", {"label": "Bob"}), ("v1", {"label": "Alice"})]
    created, duplicates = writer.write_vertices(client, "person", rows)
    assert created == 2
    assert duplicates == 1
    assert client.store.vertices["v1"]["person"] == {"label": "Alice"}
    assert client.store.vertices["v2"]["person"] == {"label": "Bob"}


def test_write_edges_dedupes_by_src_dst_rank():
    client = FakeGraphClient()
    rows = [("a", "b", 0, {"x": 1}), ("a", "b", 0, {"x": 1}), ("a", "c", 0, {"x": 2})]
    created, duplicates = writer.write_edges(client, "knows", rows)
    assert created == 2
    assert duplicates == 1
    assert len(client.store.edges) == 2


def test_write_with_retry_succeeds_after_transient_schema_propagation_delay(monkeypatch):
    monkeypatch.setattr(writer.time, "sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise QueryExecutionError("tag not found yet")

    writer.write_with_retry(flaky)
    assert attempts["count"] == 3


def test_write_with_retry_raises_after_exhausting_budget(monkeypatch):
    monkeypatch.setattr(writer.time, "sleep", lambda _seconds: None)

    def always_fails():
        raise QueryExecutionError("permanent failure")

    with pytest.raises(QueryExecutionError):
        writer.write_with_retry(always_fails)


def test_pick_label_column_prefers_name_hint():
    from graph_explorer_api.ingest.csv_inspector import ColumnProfile

    columns = [
        ColumnProfile(name="full_name", inferred_type="string", null_ratio=0, distinct_ratio=1),
        ColumnProfile(name="age", inferred_type="int", null_ratio=0, distinct_ratio=1),
    ]
    assert writer.pick_label_column(columns, ["full_name", "age"]) == "full_name"
