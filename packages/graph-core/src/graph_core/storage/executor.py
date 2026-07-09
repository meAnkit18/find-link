"""nGQL execution against NebulaGraph, producing Nebula-agnostic results."""

from __future__ import annotations

from typing import Any

from graph_core.config import GraphConfig
from graph_core.exceptions import QueryExecutionError
from graph_core.storage.connection import GraphConnectionPool
from graph_core.storage.result import QueryResult
from graph_core.storage.serialization import from_value_wrapper
from graph_core.storage.session import session_scope


class QueryExecutor:
    """Executes nGQL statements and returns Nebula-agnostic QueryResult objects."""

    def __init__(self, connection_pool: GraphConnectionPool, config: GraphConfig) -> None:
        self._connection_pool = connection_pool
        self._config = config

    def execute(self, ngql: str, use_space: bool = True) -> QueryResult:
        """Execute `ngql`. `use_space=False` skips `USE <space>` first (space administration)."""
        with session_scope(self._connection_pool, self._config, use_space=use_space) as session:
            resp = session.execute(ngql)
            if not resp.is_succeeded():
                raise QueryExecutionError(f"nGQL execution failed: {resp.error_msg()}")
            return _build_query_result(resp)


def _build_query_result(resp: Any) -> QueryResult:
    column_names = list(resp.keys())
    rows: list[dict[str, Any]] = []
    for row_index in range(resp.row_size()):
        row_values = resp.row_values(row_index)
        row = {
            column_names[col_index]: from_value_wrapper(value)
            for col_index, value in enumerate(row_values)
        }
        rows.append(row)
    return QueryResult(column_names=column_names, rows=rows)
