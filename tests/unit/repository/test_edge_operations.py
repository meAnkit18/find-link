import pytest

from graph_core.exceptions import SchemaError, ValidationError
from graph_core.model.edge import Edge
from graph_core.repository.edge_operations import EdgeOperations
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.result import QueryResult, RawEdge


class Owns(Edge):
    edge_type = "owns"

    def validate(self) -> None:
        if "since" not in self.properties:
            raise ValidationError("Owns requires since")


class FakeExecutor:
    def __init__(self):
        self.executed = []
        self.response = QueryResult(column_names=[], rows=[])

    def execute(self, ngql):
        self.executed.append(ngql)
        return self.response


def make_registry():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    return registry


def test_create_validates_and_issues_insert():
    executor = FakeExecutor()
    ops = EdgeOperations(executor, make_registry())
    ops.create(Owns("a", "b", rank=0, properties={"since": 2020}))
    assert executor.executed == ['INSERT EDGE owns(since) VALUES "a"->"b"@0:(2020)']


def test_create_raises_validation_error_before_executing():
    executor = FakeExecutor()
    ops = EdgeOperations(executor, make_registry())
    with pytest.raises(ValidationError):
        ops.create(Owns("a", "b"))
    assert executor.executed == []


def test_get_returns_none_when_no_row():
    executor = FakeExecutor()
    ops = EdgeOperations(executor, make_registry())
    assert ops.get("owns", "a", "b") is None


def test_get_deserializes_registered_edge():
    executor = FakeExecutor()
    raw = RawEdge(src="a", dst="b", edge_type="owns", rank=0, properties={"since": 2020})
    executor.response = QueryResult(column_names=["e"], rows=[{"e": raw}])
    ops = EdgeOperations(executor, make_registry())
    owns = ops.get("owns", "a", "b")
    assert isinstance(owns, Owns)
    assert owns.src == "a"
    assert owns.dst == "b"
    assert owns.properties == {"since": 2020}


def test_get_raises_schema_error_when_edge_type_unregistered():
    executor = FakeExecutor()
    raw = RawEdge(src="a", dst="b", edge_type="unregistered", rank=0, properties={})
    executor.response = QueryResult(column_names=["e"], rows=[{"e": raw}])
    ops = EdgeOperations(executor, SchemaRegistry())
    with pytest.raises(SchemaError):
        ops.get("unregistered", "a", "b")


def test_delete_issues_delete_statement():
    executor = FakeExecutor()
    ops = EdgeOperations(executor, make_registry())
    ops.delete("owns", "a", "b")
    assert executor.executed == ['DELETE EDGE owns "a"->"b"@0']
