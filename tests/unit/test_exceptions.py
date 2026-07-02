import pytest

from graph_core.exceptions import (
    GraphConnectionError,
    GraphCoreError,
    QueryExecutionError,
    SchemaError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc_cls",
    [GraphConnectionError, QueryExecutionError, SchemaError, ValidationError],
)
def test_exceptions_are_graph_core_errors(exc_cls):
    assert issubclass(exc_cls, GraphCoreError)


def test_graph_core_error_is_exception():
    assert issubclass(GraphCoreError, Exception)


def test_graph_connection_error_does_not_alias_builtin():
    assert GraphConnectionError is not ConnectionError
