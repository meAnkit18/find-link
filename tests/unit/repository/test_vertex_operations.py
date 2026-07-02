import pytest

from graph_core.exceptions import SchemaError, ValidationError
from graph_core.model.vertex import Vertex
from graph_core.repository.vertex_operations import VertexOperations
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.result import QueryResult, RawVertex


class Person(Vertex):
    tag = "person"

    def validate(self) -> None:
        if "name" not in self.properties:
            raise ValidationError("Person requires a name")


class FakeExecutor:
    def __init__(self):
        self.executed = []
        self.response = QueryResult(column_names=[], rows=[])

    def execute(self, ngql):
        self.executed.append(ngql)
        return self.response


def make_registry():
    registry = SchemaRegistry()
    registry.register_vertex("person", Person)
    return registry


def test_create_validates_and_issues_insert():
    executor = FakeExecutor()
    ops = VertexOperations(executor, make_registry())
    ops.create(Person("v1", {"name": "Alice"}))
    assert executor.executed == ['INSERT VERTEX person(name) VALUES "v1":("Alice")']


def test_create_raises_validation_error_before_executing():
    executor = FakeExecutor()
    ops = VertexOperations(executor, make_registry())
    with pytest.raises(ValidationError):
        ops.create(Person("v1", {}))
    assert executor.executed == []


def test_upsert_issues_upsert_statement():
    executor = FakeExecutor()
    ops = VertexOperations(executor, make_registry())
    ops.upsert(Person("v1", {"name": "Alice"}))
    assert executor.executed == ['UPSERT VERTEX ON person "v1" SET person.name = "Alice"']


def test_get_returns_none_when_no_row():
    executor = FakeExecutor()
    executor.response = QueryResult(column_names=[], rows=[])
    ops = VertexOperations(executor, make_registry())
    assert ops.get("person", "missing") is None


def test_get_deserializes_registered_vertex():
    executor = FakeExecutor()
    raw = RawVertex(vid="v1", tags={"person": {"name": "Alice"}})
    executor.response = QueryResult(column_names=["v"], rows=[{"v": raw}])
    ops = VertexOperations(executor, make_registry())
    person = ops.get("person", "v1")
    assert isinstance(person, Person)
    assert person.vid == "v1"
    assert person.properties == {"name": "Alice"}


def test_get_raises_schema_error_when_tag_unregistered():
    executor = FakeExecutor()
    raw = RawVertex(vid="v1", tags={"unregistered_tag": {"x": 1}})
    executor.response = QueryResult(column_names=["v"], rows=[{"v": raw}])
    ops = VertexOperations(executor, SchemaRegistry())
    with pytest.raises(SchemaError):
        ops.get("unregistered_tag", "v1")


def test_delete_issues_delete_statement():
    executor = FakeExecutor()
    ops = VertexOperations(executor, make_registry())
    ops.delete("v1")
    assert executor.executed == ['DELETE VERTEX "v1"']


def test_exists_true_and_false():
    executor = FakeExecutor()
    ops = VertexOperations(executor, make_registry())
    executor.response = QueryResult(column_names=[], rows=[])
    assert ops.exists("person", "v1") is False
    raw = RawVertex(vid="v1", tags={"person": {"name": "Alice"}})
    executor.response = QueryResult(column_names=["v"], rows=[{"v": raw}])
    assert ops.exists("person", "v1") is True
