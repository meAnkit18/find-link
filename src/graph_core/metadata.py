"""Graph administration: spaces, tag/edge/index creation, schema inspection.

Built now (not deferred) because DDL creation without inspection is unsafe:
you cannot tell whether CREATE TAG succeeded, or avoid re-creating an
existing tag/edge/index, without the ability to inspect current state.
"""

from __future__ import annotations

from graph_core.schema.models import EdgeSchema, TagSchema
from graph_core.storage.executor import QueryExecutor


class Metadata:
    """Graph administration operations: spaces, schema DDL, schema inspection."""

    def __init__(self, executor: QueryExecutor) -> None:
        self._executor = executor

    # -- spaces --

    def create_space(self, name: str, vid_type: str = "FIXED_STRING(32)") -> None:
        self._executor.execute(f"CREATE SPACE IF NOT EXISTS {name}(vid_type={vid_type})")

    def drop_space(self, name: str) -> None:
        self._executor.execute(f"DROP SPACE IF EXISTS {name}")

    def list_spaces(self) -> list[str]:
        result = self._executor.execute("SHOW SPACES")
        return [row["Name"] for row in result.rows]

    def space_exists(self, name: str) -> bool:
        return name in self.list_spaces()

    # -- tag / edge / index creation --

    def create_tag(self, schema: TagSchema) -> None:
        columns = ", ".join(f"{p.name} {p.nebula_type}" for p in schema.properties)
        self._executor.execute(f"CREATE TAG IF NOT EXISTS {schema.name}({columns})")

    def create_edge_type(self, schema: EdgeSchema) -> None:
        columns = ", ".join(f"{p.name} {p.nebula_type}" for p in schema.properties)
        self._executor.execute(f"CREATE EDGE IF NOT EXISTS {schema.name}({columns})")

    def create_tag_index(self, index_name: str, tag: str, property_names: list[str]) -> None:
        columns = ", ".join(property_names)
        self._executor.execute(
            f"CREATE TAG INDEX IF NOT EXISTS {index_name} ON {tag}({columns})"
        )

    def create_edge_index(
        self, index_name: str, edge_type: str, property_names: list[str]
    ) -> None:
        columns = ", ".join(property_names)
        self._executor.execute(
            f"CREATE EDGE INDEX IF NOT EXISTS {index_name} ON {edge_type}({columns})"
        )

    # -- inspection --

    def list_tags(self) -> list[str]:
        result = self._executor.execute("SHOW TAGS")
        return [row["Name"] for row in result.rows]

    def list_edges(self) -> list[str]:
        result = self._executor.execute("SHOW EDGES")
        return [row["Name"] for row in result.rows]

    def list_indexes(self) -> list[str]:
        result = self._executor.execute("SHOW TAG INDEXES")
        return [row["Index Name"] for row in result.rows]

    def describe_tag(self, tag: str) -> list[dict]:
        result = self._executor.execute(f"DESCRIBE TAG {tag}")
        return result.rows

    def describe_edge(self, edge_type: str) -> list[dict]:
        result = self._executor.execute(f"DESCRIBE EDGE {edge_type}")
        return result.rows
