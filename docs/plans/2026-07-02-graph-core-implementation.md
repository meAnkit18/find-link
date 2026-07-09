# graph-core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `graph-core`, a domain-agnostic Graph Data Layer over NebulaGraph, per `docs/specs/2026-07-02-graph-core-design.md`.

**Architecture:** Layered: `storage/` (only package importing `nebula3-python`, lazily via an injectable factory) → `query/builder.py` (pure nGQL string construction) → `schema/` (registry + models) → `metadata.py` (graph administration) → `repository/` (non-generic CRUD/traversal primitives) → `client.py` (public facade). `model/vertex.py` and `model/edge.py` are extension-point ABCs used across layers.

**Tech Stack:** Python ≥3.10, `nebula3-python` (runtime), `pytest` (dev). No async, no pydantic, no ORM.

## Global Constraints

- Python ≥3.10, src-layout package at `src/graph_core/`.
- Synchronous only — use `nebula3-python` directly, no asyncio, no thread pools.
- Domain-agnostic: no AML or other business concepts anywhere in this package.
- Only `graph_core/storage/*` may reference `nebula3-python`, and only lazily inside function bodies (never at module top level) — every module must import successfully with `nebula3-python` absent.
- `storage/serialization.py` uses `from __future__ import annotations` plus `TYPE_CHECKING`-guarded imports for any Nebula type hints.
- Identifier validation (tag/edge/property/space names) always goes through `graph_core/identifiers.py`'s `validate_identifier()` — never a locally re-implemented regex.
- All value literals sent to NebulaGraph go through `storage/serialization.py`'s `to_ngql_literal()` — no ad hoc string building of literals elsewhere.
- No exception name may shadow a Python builtin (`GraphConnectionError`, not `ConnectionError`).
- Every unit test must run without `nebula3-python` installed and without a running NebulaGraph instance — use the fakes in `tests/unit/storage/fakes.py`.
- `get()`-style repository/operations methods return `None` on not-found; they do not raise.
- Commit after each task with `git add <files>` + `git commit` (no `git add -A`).

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/graph_core/__init__.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: an installable/testable `graph_core` package at `src/graph_core/`, pytest configured with `pythonpath = ["src"]` so no install step is required to run tests.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "graph-core"
version = "0.1.0"
description = "Domain-agnostic Graph Data Layer for NebulaGraph"
requires-python = ">=3.10"
dependencies = [
    "nebula3-python>=3.8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = [
    "integration: requires a real NebulaGraph instance (set NEBULA_TEST_HOST to enable)",
]
```

- [ ] **Step 2: Create the empty package `__init__.py`**

```python
"""graph-core: a domain-agnostic Graph Data Layer over NebulaGraph."""
```

Path: `src/graph_core/__init__.py`

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
```

- [ ] **Step 4: Verify pytest collects cleanly with zero tests**

Run: `cd /home/ec2-user/ankit_kumar/graph-core && python3 -m pytest --collect-only`
Expected: exits 0, reports "no tests ran" (no errors, no collection failures).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/graph_core/__init__.py .gitignore
git commit -m "chore: scaffold graph-core package"
```

---

### Task 2: Identifier validation

**Files:**
- Create: `src/graph_core/identifiers.py`
- Test: `tests/unit/test_identifiers.py`

**Interfaces:**
- Produces: `validate_identifier(name: str, kind: str) -> None`, raises `ValueError` if `name` doesn't match `^[A-Za-z_][A-Za-z0-9_]*$`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_identifiers.py
import pytest

from graph_core.identifiers import validate_identifier


def test_valid_identifier_does_not_raise():
    validate_identifier("person", "tag")
    validate_identifier("_private", "tag")
    validate_identifier("Account_1", "tag")


@pytest.mark.parametrize("bad_name", ["1abc", "has-dash", "has space", "", "tag;DROP"])
def test_invalid_identifier_raises_value_error(bad_name):
    with pytest.raises(ValueError):
        validate_identifier(bad_name, "tag")


def test_error_message_includes_kind_and_name():
    with pytest.raises(ValueError, match="edge type"):
        validate_identifier("bad-name", "edge type")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_identifiers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.identifiers'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/identifiers.py
"""Shared identifier validation.

NebulaGraph's nGQL has no parameterization for identifiers (tag names, edge
type names, property names) — they must be validated against an allowlist,
not escaped. This is the single copy of that check; every layer that needs
it (config space name, query builder tag/edge/property names, metadata
tag/edge/index names) imports this rather than re-implementing the regex.
"""

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(name: str, kind: str) -> None:
    """Raise ValueError if `name` is not a safe NebulaGraph identifier."""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {kind} identifier: {name!r}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_identifiers.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/identifiers.py tests/unit/test_identifiers.py
git commit -m "feat: add identifier validation"
```

---

### Task 3: Exceptions

**Files:**
- Create: `src/graph_core/exceptions.py`
- Test: `tests/unit/test_exceptions.py`

**Interfaces:**
- Produces: `GraphCoreError`, `GraphConnectionError`, `QueryExecutionError`, `SchemaError`, `ValidationError` — all subclasses of `GraphCoreError`, which subclasses `Exception`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_exceptions.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.exceptions'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/exceptions.py
"""Exception hierarchy for graph_core.

All NebulaGraph-specific errors are translated into these before crossing
out of the storage layer, so no caller ever needs to catch a nebula3-python
exception type.
"""


class GraphCoreError(Exception):
    """Base class for all graph_core errors."""


class GraphConnectionError(GraphCoreError):
    """Raised when a connection to NebulaGraph cannot be established or is lost.

    Named to avoid shadowing Python's builtin ConnectionError.
    """


class QueryExecutionError(GraphCoreError):
    """Raised when an nGQL query fails to execute successfully."""


class SchemaError(GraphCoreError):
    """Raised for schema administration failures (tag/edge/index/space, registry)."""


class ValidationError(GraphCoreError):
    """Raised when a Vertex or Edge fails its validate() check before a write."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_exceptions.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat: add exception hierarchy"
```

---

### Task 4: Configuration

**Files:**
- Create: `src/graph_core/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `validate_identifier` from `graph_core.identifiers`.
- Produces: `GraphConfig` dataclass with fields `hosts: list[tuple[str, int]]`, `user: str`, `password: str`, `space: str`, `pool_min_size: int = 0`, `pool_max_size: int = 10`, `timeout_ms: int = 60000`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_config.py
import pytest

from graph_core.config import GraphConfig


def test_valid_config_constructs():
    config = GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user="root",
        password="nebula",
        space="test_space",
    )
    assert config.hosts == [("127.0.0.1", 9669)]
    assert config.pool_min_size == 0
    assert config.pool_max_size == 10
    assert config.timeout_ms == 60000


def test_empty_hosts_raises():
    with pytest.raises(ValueError, match="hosts"):
        GraphConfig(hosts=[], user="root", password="nebula", space="test_space")


def test_pool_max_size_below_one_raises():
    with pytest.raises(ValueError, match="pool_max_size"):
        GraphConfig(
            hosts=[("127.0.0.1", 9669)],
            user="root",
            password="nebula",
            space="test_space",
            pool_max_size=0,
        )


def test_pool_min_size_negative_raises():
    with pytest.raises(ValueError, match="pool_min_size"):
        GraphConfig(
            hosts=[("127.0.0.1", 9669)],
            user="root",
            password="nebula",
            space="test_space",
            pool_min_size=-1,
        )


def test_pool_min_size_exceeds_max_raises():
    with pytest.raises(ValueError, match="pool_min_size"):
        GraphConfig(
            hosts=[("127.0.0.1", 9669)],
            user="root",
            password="nebula",
            space="test_space",
            pool_min_size=5,
            pool_max_size=2,
        )


def test_invalid_space_name_raises():
    with pytest.raises(ValueError):
        GraphConfig(
            hosts=[("127.0.0.1", 9669)],
            user="root",
            password="nebula",
            space="bad-space",
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.config'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/config.py
"""Connection configuration for graph_core."""

from dataclasses import dataclass

from graph_core.identifiers import validate_identifier


@dataclass
class GraphConfig:
    """Configuration required to connect to a NebulaGraph cluster.

    `hosts` is a list of (host, port) tuples for the graphd service(s).
    `space` is the NebulaGraph space to USE after connecting.
    """

    hosts: list[tuple[str, int]]
    user: str
    password: str
    space: str
    pool_min_size: int = 0
    pool_max_size: int = 10
    timeout_ms: int = 60000

    def __post_init__(self) -> None:
        if not self.hosts:
            raise ValueError("GraphConfig.hosts must contain at least one (host, port) entry")
        if self.pool_max_size < 1:
            raise ValueError("GraphConfig.pool_max_size must be at least 1")
        if self.pool_min_size < 0:
            raise ValueError("GraphConfig.pool_min_size cannot be negative")
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("GraphConfig.pool_min_size cannot exceed pool_max_size")
        validate_identifier(self.space, "space")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_config.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/config.py tests/unit/test_config.py
git commit -m "feat: add GraphConfig"
```

---

### Task 5: Vertex extension point

**Files:**
- Create: `src/graph_core/model/__init__.py`
- Create: `src/graph_core/model/vertex.py`
- Test: `tests/unit/model/test_vertex.py`

**Interfaces:**
- Produces: `Vertex` ABC — `__init__(self, vid: str, properties: dict | None = None)`, abstract property `tag -> str`, `vid: str`, `properties: dict`, `validate(self) -> None` (no-op default).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/model/test_vertex.py
import pytest

from graph_core.model.vertex import Vertex


def test_vertex_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Vertex("v1")


class DummyVertex(Vertex):
    tag = "dummy"


def test_subclass_with_tag_can_be_instantiated():
    v = DummyVertex("v1", {"name": "Alice"})
    assert v.vid == "v1"
    assert v.properties == {"name": "Alice"}
    assert v.tag == "dummy"


def test_properties_default_to_empty_dict():
    v = DummyVertex("v1")
    assert v.properties == {}


def test_default_validate_is_noop():
    v = DummyVertex("v1")
    v.validate()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/model/test_vertex.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.model'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/model/__init__.py
```

```python
# src/graph_core/model/vertex.py
"""Vertex extension point.

Domain packages subclass Vertex to define their own vertex types (e.g. a
future AML package's Person, Account). graph_core never defines any concrete
Vertex subclass itself.
"""

from abc import ABC, abstractmethod
from typing import Any


class Vertex(ABC):
    """Base contract every vertex type must satisfy.

    Subclasses must implement the `tag` property to return the NebulaGraph
    tag name this vertex type maps to — commonly a plain class attribute,
    e.g. `tag = "person"`, which satisfies this abstract property.

    Subclasses should not change this constructor's signature if they rely
    on generic deserialization (VertexOperations.get()).
    """

    def __init__(self, vid: str, properties: dict[str, Any] | None = None) -> None:
        self.vid = vid
        self.properties: dict[str, Any] = properties or {}

    @property
    @abstractmethod
    def tag(self) -> str:
        ...

    def validate(self) -> None:
        """Raise ValidationError if this instance is invalid. No-op by default."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/model/test_vertex.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/model/__init__.py src/graph_core/model/vertex.py tests/unit/model/test_vertex.py
git commit -m "feat: add Vertex extension point"
```

---

### Task 6: Edge extension point

**Files:**
- Create: `src/graph_core/model/edge.py`
- Test: `tests/unit/model/test_edge.py`

**Interfaces:**
- Produces: `Edge` ABC — `__init__(self, src: str, dst: str, rank: int = 0, properties: dict | None = None)`, abstract property `edge_type -> str`, `src: str`, `dst: str`, `rank: int`, `properties: dict`, `validate(self) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/model/test_edge.py
import pytest

from graph_core.model.edge import Edge


def test_edge_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Edge("a", "b")


class DummyEdge(Edge):
    edge_type = "dummy_edge"


def test_subclass_with_edge_type_can_be_instantiated():
    e = DummyEdge("a", "b", rank=2, properties={"weight": 1.0})
    assert e.src == "a"
    assert e.dst == "b"
    assert e.rank == 2
    assert e.properties == {"weight": 1.0}
    assert e.edge_type == "dummy_edge"


def test_rank_and_properties_default():
    e = DummyEdge("a", "b")
    assert e.rank == 0
    assert e.properties == {}


def test_default_validate_is_noop():
    e = DummyEdge("a", "b")
    e.validate()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/model/test_edge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.model.edge'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/model/edge.py
"""Edge extension point.

Domain packages subclass Edge to define their own edge types (e.g. a future
AML package's OWNS, TRANSFERS). graph_core never defines any concrete Edge
subclass itself.
"""

from abc import ABC, abstractmethod
from typing import Any


class Edge(ABC):
    """Base contract every edge type must satisfy.

    Subclasses must implement the `edge_type` property to return the
    NebulaGraph edge type name — commonly a plain class attribute, e.g.
    `edge_type = "owns"`, which satisfies this abstract property.

    Subclasses should not change this constructor's signature if they rely
    on generic deserialization (EdgeOperations.get()).
    """

    def __init__(
        self,
        src: str,
        dst: str,
        rank: int = 0,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.src = src
        self.dst = dst
        self.rank = rank
        self.properties: dict[str, Any] = properties or {}

    @property
    @abstractmethod
    def edge_type(self) -> str:
        ...

    def validate(self) -> None:
        """Raise ValidationError if this instance is invalid. No-op by default."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/model/test_edge.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/model/edge.py tests/unit/model/test_edge.py
git commit -m "feat: add Edge extension point"
```

---

### Task 7: Storage result value objects

**Files:**
- Create: `src/graph_core/storage/__init__.py`
- Create: `src/graph_core/storage/result.py`
- Test: `tests/unit/storage/test_result.py`

**Interfaces:**
- Produces: `RawVertex(vid: str, tags: dict[str, dict])`, `RawEdge(src, dst, edge_type, rank, properties: dict)`, `RawPath(vertices: list[RawVertex], edges: list[RawEdge])`, `QueryResult(column_names: list[str], rows: list[dict])` with `.is_empty() -> bool` and `.single_row() -> dict | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/storage/test_result.py
from graph_core.storage.result import QueryResult, RawEdge, RawPath, RawVertex


def test_raw_vertex_defaults():
    v = RawVertex(vid="v1")
    assert v.tags == {}


def test_raw_edge_holds_fields():
    e = RawEdge(src="a", dst="b", edge_type="owns", rank=0, properties={"since": 2020})
    assert e.src == "a"
    assert e.dst == "b"
    assert e.edge_type == "owns"
    assert e.rank == 0
    assert e.properties == {"since": 2020}


def test_raw_path_defaults():
    p = RawPath()
    assert p.vertices == []
    assert p.edges == []


def test_query_result_is_empty_true_when_no_rows():
    result = QueryResult(column_names=["id"], rows=[])
    assert result.is_empty() is True
    assert result.single_row() is None


def test_query_result_is_empty_false_and_single_row():
    result = QueryResult(column_names=["id"], rows=[{"id": 1}, {"id": 2}])
    assert result.is_empty() is False
    assert result.single_row() == {"id": 1}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/storage/test_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.storage'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/storage/__init__.py
```

```python
# src/graph_core/storage/result.py
"""Nebula-agnostic result value objects.

These types are what every layer above `storage/` sees. Nothing here
imports nebula3-python.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawVertex:
    """A vertex as returned from NebulaGraph, before any domain mapping.

    `tags` maps tag name -> {property name: value} for every tag attached to
    this vertex in the result.
    """

    vid: str
    tags: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RawEdge:
    """An edge as returned from NebulaGraph, before any domain mapping."""

    src: str
    dst: str
    edge_type: str
    rank: int
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawPath:
    """An ordered sequence of vertices and the edges connecting them."""

    vertices: list[RawVertex] = field(default_factory=list)
    edges: list[RawEdge] = field(default_factory=list)


@dataclass
class QueryResult:
    """The result of executing an nGQL query.

    `rows` is a list of plain dicts (column name -> decoded Python value);
    values may themselves be RawVertex, RawEdge, RawPath, or plain Python
    scalars/lists/dicts.
    """

    column_names: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.rows) == 0

    def single_row(self) -> dict[str, Any] | None:
        """Return the first row, or None if the result has no rows."""
        return self.rows[0] if self.rows else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/storage/test_result.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/storage/__init__.py src/graph_core/storage/result.py tests/unit/storage/test_result.py
git commit -m "feat: add storage result value objects"
```

---

### Task 8: Serialization (centralized NebulaGraph value conversion)

**Files:**
- Create: `src/graph_core/storage/serialization.py`
- Create: `tests/unit/storage/fakes.py`
- Test: `tests/unit/storage/test_serialization.py`

**Interfaces:**
- Consumes: `RawVertex`, `RawEdge`, `RawPath` from `graph_core.storage.result`.
- Produces: `to_ngql_literal(value: Any) -> str`, `from_value_wrapper(value) -> Any`, `from_nebula_vertex(node) -> RawVertex`, `from_nebula_edge(relationship) -> RawEdge`, `from_nebula_path(path) -> RawPath`.

**Note:** the `Fake*` classes in `tests/unit/storage/fakes.py` stand in for
`nebula3.data.DataObject.ValueWrapper/Node/Relationship/PathWrapper`. Their method
names (`is_vertex()`, `as_node()`, `tags()`, `properties(tag_name)`,
`start_vertex_id()`, `ranking()`, etc.) are written from documented knowledge of
`nebula3-python` and must be checked against the installed package version during
integration testing — this was explicitly deferred per the design doc's decisions log.

- [ ] **Step 1: Write the fakes and the failing tests**

```python
# tests/unit/storage/fakes.py
"""Test doubles standing in for nebula3-python's wire-level types.

Method names here must match nebula3.data.DataObject's ValueWrapper/Node/
Relationship/PathWrapper API. Verify against the installed nebula3-python
version during integration testing.
"""


class FakeValueWrapper:
    def __init__(
        self,
        *,
        null=False,
        bool_=None,
        int_=None,
        double_=None,
        string_=None,
        list_=None,
        map_=None,
        vertex=None,
        edge=None,
        path=None,
    ):
        self._null = null
        self._bool = bool_
        self._int = int_
        self._double = double_
        self._string = string_
        self._list = list_
        self._map = map_
        self._vertex = vertex
        self._edge = edge
        self._path = path

    def is_null(self):
        return self._null

    def is_bool(self):
        return self._bool is not None

    def as_bool(self):
        return self._bool

    def is_int(self):
        return self._int is not None

    def as_int(self):
        return self._int

    def is_double(self):
        return self._double is not None

    def as_double(self):
        return self._double

    def is_string(self):
        return self._string is not None

    def as_string(self):
        return self._string

    def is_time(self):
        return False

    def is_date(self):
        return False

    def is_datetime(self):
        return False

    def is_list(self):
        return self._list is not None

    def as_list(self):
        return self._list

    def is_set(self):
        return False

    def is_map(self):
        return self._map is not None

    def as_map(self):
        return self._map

    def is_vertex(self):
        return self._vertex is not None

    def as_node(self):
        return self._vertex

    def is_edge(self):
        return self._edge is not None

    def as_relationship(self):
        return self._edge

    def is_path(self):
        return self._path is not None

    def as_path(self):
        return self._path


class FakeNode:
    def __init__(self, vid, tags):
        self._vid = vid
        self._tags = tags

    def get_id(self):
        return FakeValueWrapper(string_=self._vid)

    def tags(self):
        return list(self._tags.keys())

    def properties(self, tag_name):
        return self._tags[tag_name]


class FakeRelationship:
    def __init__(self, src, dst, edge_type, rank, properties):
        self._src = src
        self._dst = dst
        self._edge_type = edge_type
        self._rank = rank
        self._properties = properties

    def start_vertex_id(self):
        return FakeValueWrapper(string_=self._src)

    def end_vertex_id(self):
        return FakeValueWrapper(string_=self._dst)

    def edge_name(self):
        return self._edge_type

    def ranking(self):
        return self._rank

    def properties(self):
        return self._properties


class FakePath:
    def __init__(self, nodes, relationships):
        self._nodes = nodes
        self._relationships = relationships

    def nodes(self):
        return self._nodes

    def relationships(self):
        return self._relationships
```

```python
# tests/unit/storage/test_serialization.py
from datetime import date, datetime

from graph_core.storage.result import RawEdge, RawPath, RawVertex
from graph_core.storage.serialization import (
    from_nebula_edge,
    from_nebula_path,
    from_nebula_vertex,
    from_value_wrapper,
    to_ngql_literal,
)
from tests.unit.storage.fakes import FakeNode, FakeRelationship, FakePath, FakeValueWrapper


def test_to_ngql_literal_none():
    assert to_ngql_literal(None) == "NULL"


def test_to_ngql_literal_bool():
    assert to_ngql_literal(True) == "true"
    assert to_ngql_literal(False) == "false"


def test_to_ngql_literal_number():
    assert to_ngql_literal(42) == "42"
    assert to_ngql_literal(3.14) == "3.14"


def test_to_ngql_literal_string_escapes_quotes_and_backslashes():
    assert to_ngql_literal('He said "hi"') == '"He said \\"hi\\""'
    assert to_ngql_literal("back\\slash") == '"back\\\\slash"'


def test_to_ngql_literal_datetime_and_date():
    assert to_ngql_literal(datetime(2024, 1, 2, 3, 4, 5)) == 'datetime("2024-01-02T03:04:05")'
    assert to_ngql_literal(date(2024, 1, 2)) == 'date("2024-01-02")'


def test_to_ngql_literal_list_and_dict():
    assert to_ngql_literal([1, "a"]) == '[1, "a"]'
    assert to_ngql_literal({"x": 1}) == "{x: 1}"


def test_to_ngql_literal_unsupported_type_raises():
    import pytest

    with pytest.raises(TypeError):
        to_ngql_literal(object())


def test_from_value_wrapper_scalars():
    assert from_value_wrapper(FakeValueWrapper(null=True)) is None
    assert from_value_wrapper(FakeValueWrapper(bool_=True)) is True
    assert from_value_wrapper(FakeValueWrapper(int_=7)) == 7
    assert from_value_wrapper(FakeValueWrapper(double_=1.5)) == 1.5
    assert from_value_wrapper(FakeValueWrapper(string_="hi")) == "hi"


def test_from_value_wrapper_list_and_map():
    wrapped_list = FakeValueWrapper(list_=[FakeValueWrapper(int_=1), FakeValueWrapper(int_=2)])
    assert from_value_wrapper(wrapped_list) == [1, 2]

    wrapped_map = FakeValueWrapper(map_={"a": FakeValueWrapper(int_=1)})
    assert from_value_wrapper(wrapped_map) == {"a": 1}


def test_from_nebula_vertex_decodes_tags_and_properties():
    node = FakeNode(
        vid="v1",
        tags={"person": {"name": FakeValueWrapper(string_="Alice")}},
    )
    raw = from_nebula_vertex(node)
    assert isinstance(raw, RawVertex)
    assert raw.vid == "v1"
    assert raw.tags == {"person": {"name": "Alice"}}


def test_from_nebula_edge_decodes_fields():
    relationship = FakeRelationship(
        src="a",
        dst="b",
        edge_type="owns",
        rank=1,
        properties={"since": FakeValueWrapper(int_=2020)},
    )
    raw = from_nebula_edge(relationship)
    assert isinstance(raw, RawEdge)
    assert raw.src == "a"
    assert raw.dst == "b"
    assert raw.edge_type == "owns"
    assert raw.rank == 1
    assert raw.properties == {"since": 2020}


def test_from_nebula_path_decodes_vertices_and_edges():
    node_a = FakeNode(vid="a", tags={})
    node_b = FakeNode(vid="b", tags={})
    relationship = FakeRelationship(src="a", dst="b", edge_type="owns", rank=0, properties={})
    path = FakePath(nodes=[node_a, node_b], relationships=[relationship])
    raw = from_nebula_path(path)
    assert isinstance(raw, RawPath)
    assert [v.vid for v in raw.vertices] == ["a", "b"]
    assert len(raw.edges) == 1
    assert raw.edges[0].edge_type == "owns"


def test_from_value_wrapper_vertex_and_edge():
    node = FakeNode(vid="v1", tags={})
    assert from_value_wrapper(FakeValueWrapper(vertex=node)) == RawVertex(vid="v1", tags={})

    relationship = FakeRelationship(src="a", dst="b", edge_type="owns", rank=0, properties={})
    assert from_value_wrapper(FakeValueWrapper(edge=relationship)) == RawEdge(
        src="a", dst="b", edge_type="owns", rank=0, properties={}
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/storage/test_serialization.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.storage.serialization'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/storage/serialization.py
"""Centralized NebulaGraph <-> Python value conversion.

This is the only module that understands NebulaGraph's wire-level value
representations (ValueWrapper, Node, Relationship, PathWrapper from
nebula3-python). Every other module works with plain Python values plus
RawVertex/RawEdge/RawPath.

Uses `from __future__ import annotations` with TYPE_CHECKING-guarded
imports so this module never imports nebula3-python at runtime — every
function here operates on its argument via duck typing (calling
is_vertex()/as_node()/etc.), so it works identically against the real
nebula3-python types or the test fakes in tests/unit/storage/fakes.py.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from graph_core.storage.result import RawEdge, RawPath, RawVertex

if TYPE_CHECKING:
    from nebula3.data.DataObject import Node, PathWrapper, Relationship, ValueWrapper


def to_ngql_literal(value: Any) -> str:
    """Render a plain Python value as an nGQL literal.

    The single place Python values become nGQL literals; query/builder.py
    must never build literals by hand.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, datetime):
        return f'datetime("{value.isoformat()}")'
    if isinstance(value, date):
        return f'date("{value.isoformat()}")'
    if isinstance(value, time):
        return f'time("{value.isoformat()}")'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(to_ngql_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{k}: {to_ngql_literal(v)}" for k, v in value.items())
        return "{" + pairs + "}"
    raise TypeError(f"Cannot render value of type {type(value)!r} as an nGQL literal")


def from_value_wrapper(value: "ValueWrapper") -> Any:
    """Decode a single NebulaGraph ValueWrapper into a plain Python value."""
    if value.is_null():
        return None
    if value.is_bool():
        return value.as_bool()
    if value.is_int():
        return value.as_int()
    if value.is_double():
        return value.as_double()
    if value.is_string():
        return value.as_string()
    if value.is_list():
        return [from_value_wrapper(item) for item in value.as_list()]
    if value.is_map():
        return {key: from_value_wrapper(val) for key, val in value.as_map().items()}
    if value.is_vertex():
        return from_nebula_vertex(value.as_node())
    if value.is_edge():
        return from_nebula_edge(value.as_relationship())
    if value.is_path():
        return from_nebula_path(value.as_path())
    raise TypeError(f"Unsupported NebulaGraph value type: {value!r}")


def from_nebula_vertex(node: "Node") -> RawVertex:
    """Decode a NebulaGraph Node into a RawVertex."""
    vid = from_value_wrapper(node.get_id())
    tags: dict[str, dict[str, Any]] = {}
    for tag_name in node.tags():
        props = node.properties(tag_name)
        tags[tag_name] = {name: from_value_wrapper(val) for name, val in props.items()}
    return RawVertex(vid=str(vid), tags=tags)


def from_nebula_edge(relationship: "Relationship") -> RawEdge:
    """Decode a NebulaGraph Relationship into a RawEdge."""
    src = from_value_wrapper(relationship.start_vertex_id())
    dst = from_value_wrapper(relationship.end_vertex_id())
    props = relationship.properties()
    return RawEdge(
        src=str(src),
        dst=str(dst),
        edge_type=relationship.edge_name(),
        rank=relationship.ranking(),
        properties={name: from_value_wrapper(val) for name, val in props.items()},
    )


def from_nebula_path(path: "PathWrapper") -> RawPath:
    """Decode a NebulaGraph PathWrapper into a RawPath."""
    vertices = [from_nebula_vertex(node) for node in path.nodes()]
    edges = [from_nebula_edge(rel) for rel in path.relationships()]
    return RawPath(vertices=vertices, edges=edges)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/storage/test_serialization.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/storage/serialization.py tests/unit/storage/fakes.py tests/unit/storage/test_serialization.py
git commit -m "feat: add centralized NebulaGraph value serialization"
```

---

### Task 9: Connection pool wrapper

**Files:**
- Create: `src/graph_core/storage/connection.py`
- Modify: `tests/unit/storage/fakes.py` (add `FakePool`)
- Test: `tests/unit/storage/test_connection.py`

**Interfaces:**
- Consumes: `GraphConfig` from `graph_core.config`; `GraphConnectionError` from `graph_core.exceptions`.
- Produces: `PoolFactory = Callable[[], Any]`; `GraphConnectionPool(config: GraphConfig, pool_factory: PoolFactory | None = None)` with `.start()`, `.close()`, `.pool` (property, raises `GraphConnectionError` if not started).

- [ ] **Step 1: Add `FakePool` and write the failing tests**

```python
# Append to tests/unit/storage/fakes.py
class FakePool:
    def __init__(self, init_result=True):
        self._init_result = init_result
        self.closed = False
        self.init_args = None

    def init(self, hosts, config):
        self.init_args = (hosts, config)
        return self._init_result

    def close(self):
        self.closed = True

    def get_session(self, user, password):
        raise NotImplementedError("set on the instance by tests that need a session")
```

```python
# tests/unit/storage/test_connection.py
import pytest

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError
from graph_core.storage.connection import GraphConnectionPool
from tests.unit.storage.fakes import FakePool


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user="root",
        password="nebula",
        space="test_space",
    )


def test_start_initializes_pool_and_exposes_it():
    fake_pool = FakePool(init_result=True)
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    assert conn.pool is fake_pool
    assert fake_pool.init_args is not None


def test_start_raises_graph_connection_error_on_init_failure():
    fake_pool = FakePool(init_result=False)
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    with pytest.raises(GraphConnectionError):
        conn.start()


def test_pool_property_raises_before_start():
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: FakePool())
    with pytest.raises(GraphConnectionError):
        _ = conn.pool


def test_close_closes_started_pool():
    fake_pool = FakePool(init_result=True)
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    conn.close()
    assert fake_pool.closed is True


def test_close_before_start_is_a_noop():
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: FakePool())
    conn.close()  # must not raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/storage/test_connection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.storage.connection'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/storage/connection.py
"""NebulaGraph connection pool lifecycle.

This module never imports nebula3-python at module load time — the real
pool implementation is only constructed inside `_default_pool_factory()`,
which is never called by unit tests (they always inject a fake
`pool_factory`). This means the module — and every consumer of it — is
importable and testable without nebula3-python installed.
"""

from __future__ import annotations

from typing import Any, Callable

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError

PoolFactory = Callable[[], Any]


def _default_pool_factory() -> Any:
    from nebula3.gclient.net import ConnectionPool

    return ConnectionPool()


def _build_nebula_config(config: GraphConfig) -> Any:
    from nebula3.Config import Config as NebulaConfig

    nebula_config = NebulaConfig()
    nebula_config.min_connection_pool_size = config.pool_min_size
    nebula_config.max_connection_pool_size = config.pool_max_size
    nebula_config.timeout = config.timeout_ms
    return nebula_config


class GraphConnectionPool:
    """Wraps a NebulaGraph connection pool's lifecycle (start/close)."""

    def __init__(self, config: GraphConfig, pool_factory: PoolFactory | None = None) -> None:
        self._config = config
        self._pool_factory = pool_factory or _default_pool_factory
        self._pool: Any | None = None

    def start(self) -> None:
        """Initialize the underlying connection pool. Raises GraphConnectionError on failure."""
        pool = self._pool_factory()
        ok = pool.init(self._config.hosts, _build_nebula_config(self._config))
        if not ok:
            raise GraphConnectionError(
                f"Failed to initialize NebulaGraph connection pool for hosts {self._config.hosts}"
            )
        self._pool = pool

    def close(self) -> None:
        """Close the underlying connection pool, if started."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @property
    def pool(self) -> Any:
        """The underlying nebula3-python ConnectionPool. Raises GraphConnectionError if not started."""
        if self._pool is None:
            raise GraphConnectionError("Connection pool has not been started; call start() first")
        return self._pool
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/storage/test_connection.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/storage/connection.py tests/unit/storage/fakes.py tests/unit/storage/test_connection.py
git commit -m "feat: add GraphConnectionPool"
```

---

### Task 10: Session acquisition

**Files:**
- Create: `src/graph_core/storage/session.py`
- Modify: `tests/unit/storage/fakes.py` (add `FakeSession`, wire `FakePool.get_session`)
- Test: `tests/unit/storage/test_session.py`

**Interfaces:**
- Consumes: `GraphConnectionPool` from `graph_core.storage.connection`; `GraphConfig` from `graph_core.config`; `GraphConnectionError` from `graph_core.exceptions`.
- Produces: `session_scope(connection_pool: GraphConnectionPool, config: GraphConfig) -> ContextManager[Any]` — yields a session, always releases it, raises `GraphConnectionError` if `USE <space>` fails.

- [ ] **Step 1: Extend fakes and write the failing tests**

```python
# Append to tests/unit/storage/fakes.py
class FakeUseResultSet:
    def __init__(self, succeeded=True, error_msg=""):
        self._succeeded = succeeded
        self._error_msg = error_msg

    def is_succeeded(self):
        return self._succeeded

    def error_msg(self):
        return self._error_msg


class FakeSession:
    def __init__(self, use_succeeds=True):
        self.released = False
        self.executed = []
        self._use_succeeds = use_succeeds

    def execute(self, ngql):
        self.executed.append(ngql)
        return FakeUseResultSet(succeeded=self._use_succeeds, error_msg="space not found")

    def release(self):
        self.released = True
```

```python
# tests/unit/storage/test_session.py
import pytest

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError
from graph_core.storage.connection import GraphConnectionPool
from graph_core.storage.session import session_scope
from tests.unit.storage.fakes import FakePool, FakeSession


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def _pool_with_session(session):
    fake_pool = FakePool(init_result=True)
    fake_pool.get_session = lambda user, password: session
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    return conn


def test_session_scope_yields_session_and_switches_space():
    session = FakeSession(use_succeeds=True)
    conn = _pool_with_session(session)
    with session_scope(conn, make_config()) as s:
        assert s is session
    assert session.executed == ["USE test_space"]


def test_session_scope_releases_session_on_success():
    session = FakeSession(use_succeeds=True)
    conn = _pool_with_session(session)
    with session_scope(conn, make_config()):
        pass
    assert session.released is True


def test_session_scope_releases_session_even_on_exception():
    session = FakeSession(use_succeeds=True)
    conn = _pool_with_session(session)
    with pytest.raises(RuntimeError):
        with session_scope(conn, make_config()):
            raise RuntimeError("boom")
    assert session.released is True


def test_session_scope_raises_graph_connection_error_when_use_fails():
    session = FakeSession(use_succeeds=False)
    conn = _pool_with_session(session)
    with pytest.raises(GraphConnectionError):
        with session_scope(conn, make_config()):
            pass
    assert session.released is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/storage/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.storage.session'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/storage/session.py
"""Session acquisition/release against a NebulaGraph connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError
from graph_core.storage.connection import GraphConnectionPool


@contextmanager
def session_scope(connection_pool: GraphConnectionPool, config: GraphConfig) -> Iterator[Any]:
    """Acquire a session from the pool for the configured space, releasing it afterward."""
    session = connection_pool.pool.get_session(config.user, config.password)
    try:
        use_resp = session.execute(f"USE {config.space}")
        if not use_resp.is_succeeded():
            raise GraphConnectionError(
                f"Failed to switch to space {config.space!r}: {use_resp.error_msg()}"
            )
        yield session
    finally:
        session.release()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/storage/test_session.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/storage/session.py tests/unit/storage/fakes.py tests/unit/storage/test_session.py
git commit -m "feat: add NebulaGraph session_scope"
```

---

### Task 11: Query executor

**Files:**
- Create: `src/graph_core/storage/executor.py`
- Modify: `tests/unit/storage/fakes.py` (add `FakeResultSet`, extend `FakeSession.execute` to look up canned responses)
- Test: `tests/unit/storage/test_executor.py`

**Interfaces:**
- Consumes: `GraphConnectionPool`, `session_scope` from `graph_core.storage`; `QueryExecutionError` from `graph_core.exceptions`; `from_value_wrapper` from `graph_core.storage.serialization`; `QueryResult` from `graph_core.storage.result`.
- Produces: `QueryExecutor(connection_pool: GraphConnectionPool, config: GraphConfig)` with `.execute(ngql: str) -> QueryResult`.

- [ ] **Step 1: Extend fakes and write the failing tests**

```python
# Append to tests/unit/storage/fakes.py
class FakeResultSet:
    def __init__(self, succeeded=True, error_msg="", column_names=None, rows=None):
        self._succeeded = succeeded
        self._error_msg = error_msg
        self._column_names = column_names or []
        self._rows = rows or []  # list of list[FakeValueWrapper]

    def is_succeeded(self):
        return self._succeeded

    def error_msg(self):
        return self._error_msg

    def keys(self):
        return self._column_names

    def row_size(self):
        return len(self._rows)

    def row_values(self, index):
        return self._rows[index]


class FakeQuerySession(FakeSession):
    """A FakeSession where the second execute() call (the real query) returns a canned FakeResultSet."""

    def __init__(self, query_result: FakeResultSet, use_succeeds=True):
        super().__init__(use_succeeds=use_succeeds)
        self._query_result = query_result

    def execute(self, ngql):
        self.executed.append(ngql)
        if ngql.startswith("USE "):
            return FakeUseResultSet(succeeded=self._use_succeeds, error_msg="space not found")
        return self._query_result
```

```python
# tests/unit/storage/test_executor.py
import pytest

from graph_core.config import GraphConfig
from graph_core.exceptions import QueryExecutionError
from graph_core.storage.connection import GraphConnectionPool
from graph_core.storage.executor import QueryExecutor
from tests.unit.storage.fakes import FakePool, FakeQuerySession, FakeResultSet, FakeValueWrapper


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def _executor_with(query_result):
    session = FakeQuerySession(query_result=query_result)
    fake_pool = FakePool(init_result=True)
    fake_pool.get_session = lambda user, password: session
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    return QueryExecutor(conn, make_config()), session


def test_execute_returns_decoded_rows():
    result_set = FakeResultSet(
        succeeded=True,
        column_names=["name", "age"],
        rows=[[FakeValueWrapper(string_="Alice"), FakeValueWrapper(int_=30)]],
    )
    executor, _ = _executor_with(result_set)
    result = executor.execute("FETCH PROP ON person \"v1\" YIELD VERTEX AS v")
    assert result.column_names == ["name", "age"]
    assert result.rows == [{"name": "Alice", "age": 30}]


def test_execute_raises_query_execution_error_on_failure():
    result_set = FakeResultSet(succeeded=False, error_msg="syntax error")
    executor, _ = _executor_with(result_set)
    with pytest.raises(QueryExecutionError, match="syntax error"):
        executor.execute("BAD QUERY")


def test_execute_releases_session():
    result_set = FakeResultSet(succeeded=True, column_names=[], rows=[])
    executor, session = _executor_with(result_set)
    executor.execute("SHOW TAGS")
    assert session.released is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/storage/test_executor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.storage.executor'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/storage/executor.py
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

    def execute(self, ngql: str) -> QueryResult:
        with session_scope(self._connection_pool, self._config) as session:
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/storage/test_executor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/storage/executor.py tests/unit/storage/fakes.py tests/unit/storage/test_executor.py
git commit -m "feat: add QueryExecutor"
```

---

### Task 12: Query builder

**Files:**
- Create: `src/graph_core/query/__init__.py`
- Create: `src/graph_core/query/builder.py`
- Test: `tests/unit/query/test_builder.py`

**Interfaces:**
- Consumes: `validate_identifier` from `graph_core.identifiers`; `to_ngql_literal` from `graph_core.storage.serialization`.
- Produces: `build_insert_vertex`, `build_upsert_vertex`, `build_fetch_vertex`, `build_delete_vertex`, `build_insert_edge`, `build_fetch_edge`, `build_delete_edge`, `build_go_neighbors` — all pure `(...) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/query/test_builder.py
import pytest

from graph_core.query.builder import (
    build_delete_edge,
    build_delete_vertex,
    build_fetch_edge,
    build_fetch_vertex,
    build_go_neighbors,
    build_insert_edge,
    build_insert_vertex,
    build_upsert_vertex,
)


def test_build_insert_vertex():
    ngql = build_insert_vertex("person", "v1", {"name": "Alice", "age": 30})
    assert ngql == 'INSERT VERTEX person(name, age) VALUES "v1":("Alice", 30)'


def test_build_insert_vertex_rejects_bad_tag():
    with pytest.raises(ValueError):
        build_insert_vertex("bad-tag", "v1", {"name": "Alice"})


def test_build_upsert_vertex():
    ngql = build_upsert_vertex("person", "v1", {"age": 31})
    assert ngql == 'UPSERT VERTEX ON person "v1" SET person.age = 31'


def test_build_fetch_vertex():
    ngql = build_fetch_vertex("person", "v1")
    assert ngql == 'FETCH PROP ON person "v1" YIELD VERTEX AS v'


def test_build_delete_vertex():
    ngql = build_delete_vertex("v1")
    assert ngql == 'DELETE VERTEX "v1"'


def test_build_insert_edge():
    ngql = build_insert_edge("owns", "a", "b", 0, {"since": 2020})
    assert ngql == 'INSERT EDGE owns(since) VALUES "a"->"b"@0:(2020)'


def test_build_fetch_edge():
    ngql = build_fetch_edge("owns", "a", "b", 0)
    assert ngql == 'FETCH PROP ON owns "a"->"b"@0 YIELD EDGE AS e'


def test_build_delete_edge():
    ngql = build_delete_edge("owns", "a", "b", 0)
    assert ngql == 'DELETE EDGE owns "a"->"b"@0'


def test_build_go_neighbors_out():
    ngql = build_go_neighbors("v1", "owns", "out")
    assert ngql == (
        'GO FROM "v1" OVER owns YIELD DISTINCT dst(edge) AS id '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    )


def test_build_go_neighbors_in():
    ngql = build_go_neighbors("v1", "owns", "in")
    assert "REVERSELY" in ngql


def test_build_go_neighbors_both_any_edge_type():
    ngql = build_go_neighbors("v1", None, "both")
    assert "OVER * BIDIRECT" in ngql


def test_build_go_neighbors_rejects_bad_direction():
    with pytest.raises(ValueError):
        build_go_neighbors("v1", "owns", "sideways")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/query/test_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.query'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/query/__init__.py
```

```python
# src/graph_core/query/builder.py
"""Pure nGQL string construction. No I/O, no NebulaGraph client import."""

from __future__ import annotations

from typing import Any

from graph_core.identifiers import validate_identifier
from graph_core.storage.serialization import to_ngql_literal


def _format_vid(vid: str) -> str:
    return to_ngql_literal(str(vid))


def _format_insert_properties(properties: dict[str, Any]) -> tuple[str, str]:
    names = list(properties.keys())
    for name in names:
        validate_identifier(name, "property")
    columns = ", ".join(names)
    values = ", ".join(to_ngql_literal(properties[name]) for name in names)
    return columns, values


def build_insert_vertex(tag: str, vid: str, properties: dict[str, Any]) -> str:
    validate_identifier(tag, "tag")
    columns, values = _format_insert_properties(properties)
    return f"INSERT VERTEX {tag}({columns}) VALUES {_format_vid(vid)}:({values})"


def build_upsert_vertex(tag: str, vid: str, properties: dict[str, Any]) -> str:
    validate_identifier(tag, "tag")
    for name in properties:
        validate_identifier(name, "property")
    assignments = ", ".join(
        f"{tag}.{name} = {to_ngql_literal(value)}" for name, value in properties.items()
    )
    return f"UPSERT VERTEX ON {tag} {_format_vid(vid)} SET {assignments}"


def build_fetch_vertex(tag: str, vid: str) -> str:
    validate_identifier(tag, "tag")
    return f"FETCH PROP ON {tag} {_format_vid(vid)} YIELD VERTEX AS v"


def build_delete_vertex(vid: str) -> str:
    return f"DELETE VERTEX {_format_vid(vid)}"


def build_insert_edge(
    edge_type: str, src: str, dst: str, rank: int, properties: dict[str, Any]
) -> str:
    validate_identifier(edge_type, "edge type")
    columns, values = _format_insert_properties(properties)
    return (
        f"INSERT EDGE {edge_type}({columns}) VALUES "
        f"{_format_vid(src)}->{_format_vid(dst)}@{rank}:({values})"
    )


def build_fetch_edge(edge_type: str, src: str, dst: str, rank: int) -> str:
    validate_identifier(edge_type, "edge type")
    return (
        f"FETCH PROP ON {edge_type} {_format_vid(src)}->{_format_vid(dst)}@{rank} "
        f"YIELD EDGE AS e"
    )


def build_delete_edge(edge_type: str, src: str, dst: str, rank: int) -> str:
    validate_identifier(edge_type, "edge type")
    return f"DELETE EDGE {edge_type} {_format_vid(src)}->{_format_vid(dst)}@{rank}"


def build_go_neighbors(vid: str, edge_type: str | None, direction: str) -> str:
    if direction not in ("out", "in", "both"):
        raise ValueError(f"direction must be 'out', 'in', or 'both', got {direction!r}")

    edge_clause = "*"
    if edge_type is not None:
        validate_identifier(edge_type, "edge type")
        edge_clause = edge_type

    if direction == "out":
        over_clause = f"OVER {edge_clause}"
    elif direction == "in":
        over_clause = f"OVER {edge_clause} REVERSELY"
    else:
        over_clause = f"OVER {edge_clause} BIDIRECT"

    return (
        f"GO FROM {_format_vid(vid)} {over_clause} YIELD DISTINCT dst(edge) AS id "
        f"| FETCH PROP ON * $-.id YIELD VERTEX AS v"
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/query/test_builder.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/query/__init__.py src/graph_core/query/builder.py tests/unit/query/test_builder.py
git commit -m "feat: add nGQL query builder"
```

---

### Task 13: Schema models

**Files:**
- Create: `src/graph_core/schema/__init__.py`
- Create: `src/graph_core/schema/models.py`
- Test: `tests/unit/schema/test_models.py`

**Interfaces:**
- Produces: `PropertyDefinition(name, nebula_type, nullable=True, default=None)`, `TagSchema(name, properties=())`, `EdgeSchema(name, properties=())` — all frozen dataclasses.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/schema/test_models.py
from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema


def test_property_definition_defaults():
    prop = PropertyDefinition(name="age", nebula_type="int64")
    assert prop.nullable is True
    assert prop.default is None


def test_tag_schema_holds_properties():
    prop = PropertyDefinition(name="name", nebula_type="string")
    tag = TagSchema(name="person", properties=(prop,))
    assert tag.name == "person"
    assert tag.properties == (prop,)


def test_edge_schema_defaults_to_no_properties():
    edge = EdgeSchema(name="owns")
    assert edge.properties == ()


def test_property_definition_is_frozen():
    prop = PropertyDefinition(name="age", nebula_type="int64")
    try:
        prop.name = "changed"
        assert False, "expected FrozenInstanceError"
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/schema/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.schema'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/schema/__init__.py
```

```python
# src/graph_core/schema/models.py
"""Pure schema definitions: tag and edge type property shapes.

Data only; SchemaRegistry and Metadata attach behavior to these.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PropertyDefinition:
    """A single property in a NebulaGraph tag or edge type schema."""

    name: str
    nebula_type: str  # e.g. "string", "int64", "double", "bool", "timestamp"
    nullable: bool = True
    default: object | None = None


@dataclass(frozen=True)
class TagSchema:
    """The NebulaGraph schema for one tag (vertex type)."""

    name: str
    properties: tuple[PropertyDefinition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EdgeSchema:
    """The NebulaGraph schema for one edge type."""

    name: str
    properties: tuple[PropertyDefinition, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/schema/test_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/schema/__init__.py src/graph_core/schema/models.py tests/unit/schema/test_models.py
git commit -m "feat: add schema model definitions"
```

---

### Task 14: Schema registry

**Files:**
- Create: `src/graph_core/schema/registry.py`
- Test: `tests/unit/schema/test_registry.py`

**Interfaces:**
- Consumes: `Vertex` from `graph_core.model.vertex`; `Edge` from `graph_core.model.edge`; `SchemaError` from `graph_core.exceptions`.
- Produces: `SchemaRegistry()` with `.register_vertex(tag: str, vertex_cls: type[Vertex])`, `.register_edge(edge_type: str, edge_cls: type[Edge])`, `.get_vertex_class(tag: str) -> type[Vertex] | None`, `.get_edge_class(edge_type: str) -> type[Edge] | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/schema/test_registry.py
import pytest

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.model.vertex import Vertex
from graph_core.schema.registry import SchemaRegistry


class Person(Vertex):
    tag = "person"


class Owns(Edge):
    edge_type = "owns"


def test_register_and_get_vertex_class():
    registry = SchemaRegistry()
    registry.register_vertex("person", Person)
    assert registry.get_vertex_class("person") is Person


def test_get_vertex_class_returns_none_when_unregistered():
    registry = SchemaRegistry()
    assert registry.get_vertex_class("unknown") is None


def test_register_vertex_twice_raises_schema_error():
    registry = SchemaRegistry()
    registry.register_vertex("person", Person)
    with pytest.raises(SchemaError):
        registry.register_vertex("person", Person)


def test_register_and_get_edge_class():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    assert registry.get_edge_class("owns") is Owns


def test_get_edge_class_returns_none_when_unregistered():
    registry = SchemaRegistry()
    assert registry.get_edge_class("unknown") is None


def test_register_edge_twice_raises_schema_error():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    with pytest.raises(SchemaError):
        registry.register_edge("owns", Owns)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/schema/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.schema.registry'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/schema/registry.py
"""SchemaRegistry: the extension point mapping tag/edge-type names to Python classes.

Future domain packages call register_vertex()/register_edge() at import
time to make their Vertex/Edge subclasses resolvable during
deserialization.
"""

from __future__ import annotations

from typing import Type

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.model.vertex import Vertex


class SchemaRegistry:
    def __init__(self) -> None:
        self._vertex_classes: dict[str, Type[Vertex]] = {}
        self._edge_classes: dict[str, Type[Edge]] = {}

    def register_vertex(self, tag: str, vertex_cls: Type[Vertex]) -> None:
        if tag in self._vertex_classes:
            raise SchemaError(f"Vertex tag {tag!r} is already registered")
        self._vertex_classes[tag] = vertex_cls

    def register_edge(self, edge_type: str, edge_cls: Type[Edge]) -> None:
        if edge_type in self._edge_classes:
            raise SchemaError(f"Edge type {edge_type!r} is already registered")
        self._edge_classes[edge_type] = edge_cls

    def get_vertex_class(self, tag: str) -> Type[Vertex] | None:
        return self._vertex_classes.get(tag)

    def get_edge_class(self, edge_type: str) -> Type[Edge] | None:
        return self._edge_classes.get(edge_type)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/schema/test_registry.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/schema/registry.py tests/unit/schema/test_registry.py
git commit -m "feat: add SchemaRegistry"
```

---

### Task 15: Metadata (graph administration)

**Files:**
- Create: `src/graph_core/metadata.py`
- Test: `tests/unit/test_metadata.py`

**Interfaces:**
- Consumes: `QueryExecutor` from `graph_core.storage.executor`; `TagSchema`, `EdgeSchema` from `graph_core.schema.models`; `QueryResult` from `graph_core.storage.result`.
- Produces: `Metadata(executor: QueryExecutor)` with `.create_space`, `.drop_space`, `.list_spaces`, `.space_exists`, `.create_tag`, `.create_edge_type`, `.create_tag_index`, `.create_edge_index`, `.list_tags`, `.list_edges`, `.list_indexes`, `.describe_tag`, `.describe_edge`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_metadata.py
from graph_core.metadata import Metadata
from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema
from graph_core.storage.result import QueryResult


class FakeExecutor:
    def __init__(self):
        self.executed = []
        self.responses = {}

    def execute(self, ngql):
        self.executed.append(ngql)
        return self.responses.get(ngql, QueryResult(column_names=[], rows=[]))


def test_create_space_issues_create_space_statement():
    executor = FakeExecutor()
    Metadata(executor).create_space("aml")
    assert executor.executed == ['CREATE SPACE IF NOT EXISTS aml(vid_type=FIXED_STRING(32))']


def test_drop_space_issues_drop_space_statement():
    executor = FakeExecutor()
    Metadata(executor).drop_space("aml")
    assert executor.executed == ["DROP SPACE IF EXISTS aml"]


def test_list_spaces_extracts_names():
    executor = FakeExecutor()
    executor.responses["SHOW SPACES"] = QueryResult(
        column_names=["Name"], rows=[{"Name": "aml"}, {"Name": "test_space"}]
    )
    names = Metadata(executor).list_spaces()
    assert names == ["aml", "test_space"]


def test_space_exists_true_and_false():
    executor = FakeExecutor()
    executor.responses["SHOW SPACES"] = QueryResult(column_names=["Name"], rows=[{"Name": "aml"}])
    metadata = Metadata(executor)
    assert metadata.space_exists("aml") is True
    assert metadata.space_exists("missing") is False


def test_create_tag_builds_ddl_from_schema():
    executor = FakeExecutor()
    schema = TagSchema(
        name="person",
        properties=(PropertyDefinition(name="name", nebula_type="string"),),
    )
    Metadata(executor).create_tag(schema)
    assert executor.executed == ["CREATE TAG IF NOT EXISTS person(name string)"]


def test_create_edge_type_builds_ddl_from_schema():
    executor = FakeExecutor()
    schema = EdgeSchema(
        name="owns",
        properties=(PropertyDefinition(name="since", nebula_type="int64"),),
    )
    Metadata(executor).create_edge_type(schema)
    assert executor.executed == ["CREATE EDGE IF NOT EXISTS owns(since int64)"]


def test_create_tag_index():
    executor = FakeExecutor()
    Metadata(executor).create_tag_index("person_name_idx", "person", ["name"])
    assert executor.executed == [
        "CREATE TAG INDEX IF NOT EXISTS person_name_idx ON person(name)"
    ]


def test_list_tags_and_edges_and_indexes():
    executor = FakeExecutor()
    executor.responses["SHOW TAGS"] = QueryResult(column_names=["Name"], rows=[{"Name": "person"}])
    executor.responses["SHOW EDGES"] = QueryResult(column_names=["Name"], rows=[{"Name": "owns"}])
    executor.responses["SHOW TAG INDEXES"] = QueryResult(
        column_names=["Index Name"], rows=[{"Index Name": "person_name_idx"}]
    )
    metadata = Metadata(executor)
    assert metadata.list_tags() == ["person"]
    assert metadata.list_edges() == ["owns"]
    assert metadata.list_indexes() == ["person_name_idx"]


def test_describe_tag_and_edge_return_rows():
    executor = FakeExecutor()
    executor.responses["DESCRIBE TAG person"] = QueryResult(
        column_names=["Field"], rows=[{"Field": "name"}]
    )
    metadata = Metadata(executor)
    assert metadata.describe_tag("person") == [{"Field": "name"}]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_metadata.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.metadata'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/metadata.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_metadata.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/metadata.py tests/unit/test_metadata.py
git commit -m "feat: add Metadata graph administration module"
```

---

### Task 16: Vertex operations primitive

**Files:**
- Create: `src/graph_core/repository/__init__.py`
- Create: `src/graph_core/repository/vertex_operations.py`
- Test: `tests/unit/repository/test_vertex_operations.py`

**Interfaces:**
- Consumes: `Vertex` from `graph_core.model.vertex`; `build_insert_vertex`, `build_upsert_vertex`, `build_fetch_vertex`, `build_delete_vertex` from `graph_core.query.builder`; `SchemaRegistry` from `graph_core.schema.registry`; `QueryExecutor` from `graph_core.storage.executor`; `RawVertex` from `graph_core.storage.result`; `SchemaError` from `graph_core.exceptions`.
- Produces: `VertexOperations(executor: QueryExecutor, registry: SchemaRegistry)` with `.create(vertex)`, `.upsert(vertex)`, `.get(tag, vid) -> Vertex | None`, `.delete(vid)`, `.exists(tag, vid) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/repository/test_vertex_operations.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/repository/test_vertex_operations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.repository'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/repository/__init__.py
```

```python
# src/graph_core/repository/vertex_operations.py
"""Non-generic vertex CRUD primitives.

Future domain repositories (e.g. a PersonRepository in an AML package)
compose this class as a dependency rather than inheriting from a generic
repository base class — that keeps this primitive simple while letting
domain repositories add whatever query methods they actually need.
"""

from __future__ import annotations

from typing import Optional, Type

from graph_core.exceptions import SchemaError
from graph_core.model.vertex import Vertex
from graph_core.query.builder import (
    build_delete_vertex,
    build_fetch_vertex,
    build_insert_vertex,
    build_upsert_vertex,
)
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawVertex


class VertexOperations:
    """Vertex CRUD primitives, operating on any Vertex subclass via SchemaRegistry."""

    def __init__(self, executor: QueryExecutor, registry: SchemaRegistry) -> None:
        self._executor = executor
        self._registry = registry

    def create(self, vertex: Vertex) -> None:
        vertex.validate()
        ngql = build_insert_vertex(vertex.tag, vertex.vid, vertex.properties)
        self._executor.execute(ngql)

    def upsert(self, vertex: Vertex) -> None:
        vertex.validate()
        ngql = build_upsert_vertex(vertex.tag, vertex.vid, vertex.properties)
        self._executor.execute(ngql)

    def get(self, tag: str, vid: str) -> Optional[Vertex]:
        ngql = build_fetch_vertex(tag, vid)
        result = self._executor.execute(ngql)
        row = result.single_row()
        if row is None:
            return None
        raw = row.get("v")
        if not isinstance(raw, RawVertex):
            return None
        return self._to_domain(raw)

    def delete(self, vid: str) -> None:
        ngql = build_delete_vertex(vid)
        self._executor.execute(ngql)

    def exists(self, tag: str, vid: str) -> bool:
        return self.get(tag, vid) is not None

    def _to_domain(self, raw: RawVertex) -> Vertex:
        vertex_cls: Type[Vertex] | None = None
        properties: dict = {}
        for tag_name, props in raw.tags.items():
            cls = self._registry.get_vertex_class(tag_name)
            if cls is not None:
                vertex_cls = cls
                properties = props
                break
        if vertex_cls is None:
            raise SchemaError(
                f"No Vertex class registered for any tag on vertex {raw.vid!r}: {list(raw.tags)}"
            )
        return vertex_cls(vid=raw.vid, properties=properties)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/repository/test_vertex_operations.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/repository/__init__.py src/graph_core/repository/vertex_operations.py tests/unit/repository/test_vertex_operations.py
git commit -m "feat: add VertexOperations"
```

---

### Task 17: Edge operations primitive

**Files:**
- Create: `src/graph_core/repository/edge_operations.py`
- Test: `tests/unit/repository/test_edge_operations.py`

**Interfaces:**
- Consumes: `Edge` from `graph_core.model.edge`; `build_insert_edge`, `build_fetch_edge`, `build_delete_edge` from `graph_core.query.builder`; `SchemaRegistry` from `graph_core.schema.registry`; `QueryExecutor` from `graph_core.storage.executor`; `RawEdge` from `graph_core.storage.result`; `SchemaError` from `graph_core.exceptions`.
- Produces: `EdgeOperations(executor: QueryExecutor, registry: SchemaRegistry)` with `.create(edge)`, `.get(edge_type, src, dst, rank=0) -> Edge | None`, `.delete(edge_type, src, dst, rank=0)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/repository/test_edge_operations.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/repository/test_edge_operations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.repository.edge_operations'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/repository/edge_operations.py
"""Non-generic edge CRUD primitives.

Mirrors VertexOperations: future domain repositories compose this rather
than inheriting from a generic repository base class.
"""

from __future__ import annotations

from typing import Optional, Type

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.query.builder import build_delete_edge, build_fetch_edge, build_insert_edge
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawEdge


class EdgeOperations:
    """Edge CRUD primitives, operating on any Edge subclass via SchemaRegistry."""

    def __init__(self, executor: QueryExecutor, registry: SchemaRegistry) -> None:
        self._executor = executor
        self._registry = registry

    def create(self, edge: Edge) -> None:
        edge.validate()
        ngql = build_insert_edge(edge.edge_type, edge.src, edge.dst, edge.rank, edge.properties)
        self._executor.execute(ngql)

    def get(self, edge_type: str, src: str, dst: str, rank: int = 0) -> Optional[Edge]:
        ngql = build_fetch_edge(edge_type, src, dst, rank)
        result = self._executor.execute(ngql)
        row = result.single_row()
        if row is None:
            return None
        raw = row.get("e")
        if not isinstance(raw, RawEdge):
            return None
        return self._to_domain(raw)

    def delete(self, edge_type: str, src: str, dst: str, rank: int = 0) -> None:
        ngql = build_delete_edge(edge_type, src, dst, rank)
        self._executor.execute(ngql)

    def _to_domain(self, raw: RawEdge) -> Edge:
        edge_cls: Type[Edge] | None = self._registry.get_edge_class(raw.edge_type)
        if edge_cls is None:
            raise SchemaError(f"No Edge class registered for edge type {raw.edge_type!r}")
        return edge_cls(src=raw.src, dst=raw.dst, rank=raw.rank, properties=raw.properties)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/repository/test_edge_operations.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/repository/edge_operations.py tests/unit/repository/test_edge_operations.py
git commit -m "feat: add EdgeOperations"
```

---

### Task 18: Traversal

**Files:**
- Create: `src/graph_core/repository/traversal.py`
- Test: `tests/unit/repository/test_traversal.py`

**Interfaces:**
- Consumes: `build_go_neighbors` from `graph_core.query.builder`; `QueryExecutor` from `graph_core.storage.executor`; `RawVertex` from `graph_core.storage.result`.
- Produces: `Traversal(executor: QueryExecutor)` with `.get_neighbors(vid, edge_type=None, direction="out") -> list[RawVertex]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/repository/test_traversal.py
from graph_core.repository.traversal import Traversal
from graph_core.storage.result import QueryResult, RawVertex


class FakeExecutor:
    def __init__(self, response):
        self.executed = []
        self.response = response

    def execute(self, ngql):
        self.executed.append(ngql)
        return self.response


def test_get_neighbors_returns_raw_vertices():
    raw_a = RawVertex(vid="a", tags={"person": {"name": "Alice"}})
    raw_b = RawVertex(vid="b", tags={"person": {"name": "Bob"}})
    response = QueryResult(column_names=["v"], rows=[{"v": raw_a}, {"v": raw_b}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    neighbors = traversal.get_neighbors("v1", edge_type="owns", direction="out")
    assert neighbors == [raw_a, raw_b]
    assert executor.executed == [
        'GO FROM "v1" OVER owns YIELD DISTINCT dst(edge) AS id '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    ]


def test_get_neighbors_ignores_non_vertex_rows():
    response = QueryResult(column_names=["v"], rows=[{"v": "not-a-vertex"}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    assert traversal.get_neighbors("v1") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/repository/test_traversal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.repository.traversal'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/repository/traversal.py
"""Traversal: graph-navigation operations.

get_neighbors() is the only traversal operation built now — more advanced
graph algorithms (shortest path, subgraph extraction, PageRank, etc.) are
explicitly deferred until a real consumer needs them.
"""

from __future__ import annotations

from typing import Optional

from graph_core.query.builder import build_go_neighbors
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawVertex


class Traversal:
    def __init__(self, executor: QueryExecutor) -> None:
        self._executor = executor

    def get_neighbors(
        self, vid: str, edge_type: Optional[str] = None, direction: str = "out"
    ) -> list[RawVertex]:
        ngql = build_go_neighbors(vid, edge_type, direction)
        result = self._executor.execute(ngql)
        neighbors: list[RawVertex] = []
        for row in result.rows:
            vertex = row.get("v")
            if isinstance(vertex, RawVertex):
                neighbors.append(vertex)
        return neighbors
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/repository/test_traversal.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/graph_core/repository/traversal.py tests/unit/repository/test_traversal.py
git commit -m "feat: add Traversal"
```

---

### Task 19: GraphClient facade

**Files:**
- Create: `src/graph_core/client.py`
- Modify: `src/graph_core/__init__.py` (export `GraphClient`)
- Test: `tests/unit/test_client.py`

**Interfaces:**
- Consumes: `GraphConfig`, `SchemaRegistry`, `PoolFactory`, `GraphConnectionPool`, `QueryExecutor`, `VertexOperations`, `EdgeOperations`, `Traversal`, `Metadata`, `QueryResult`.
- Produces: `GraphClient(config, registry=None, pool_factory=None)` with `.connect()`, `.close()`, `.execute_raw(ngql) -> QueryResult`, `.vertices`, `.edges`, `.traversal`, `.metadata` attributes, and context-manager support.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_client.py
from graph_core.client import GraphClient
from graph_core.config import GraphConfig
from graph_core.repository.edge_operations import EdgeOperations
from graph_core.repository.traversal import Traversal
from graph_core.repository.vertex_operations import VertexOperations
from graph_core.metadata import Metadata


class FakePool:
    def __init__(self):
        self.closed = False
        self.init_args = None

    def init(self, hosts, config):
        self.init_args = (hosts, config)
        return True

    def close(self):
        self.closed = True

    def get_session(self, user, password):
        raise NotImplementedError


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def test_client_exposes_primitives():
    client = GraphClient(make_config(), pool_factory=FakePool)
    assert isinstance(client.vertices, VertexOperations)
    assert isinstance(client.edges, EdgeOperations)
    assert isinstance(client.traversal, Traversal)
    assert isinstance(client.metadata, Metadata)


def test_connect_starts_pool_and_close_closes_it():
    fake_pool = FakePool()
    client = GraphClient(make_config(), pool_factory=lambda: fake_pool)
    client.connect()
    assert fake_pool.init_args is not None
    client.close()
    assert fake_pool.closed is True


def test_context_manager_connects_and_closes():
    fake_pool = FakePool()
    with GraphClient(make_config(), pool_factory=lambda: fake_pool) as client:
        assert fake_pool.init_args is not None
    assert fake_pool.closed is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_core.client'`

- [ ] **Step 3: Implement**

```python
# src/graph_core/client.py
"""GraphClient: the single public entry point for graph-core consumers.

Wires GraphConfig to the connection pool and exposes the repository
primitives, Metadata, and an execute_raw() escape hatch. Nothing outside
this file (and storage/) needs to know NebulaGraph exists.
"""

from __future__ import annotations

from graph_core.config import GraphConfig
from graph_core.metadata import Metadata
from graph_core.repository.edge_operations import EdgeOperations
from graph_core.repository.traversal import Traversal
from graph_core.repository.vertex_operations import VertexOperations
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.connection import GraphConnectionPool, PoolFactory
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import QueryResult


class GraphClient:
    """Single public facade wiring config to storage, schema, and repository primitives."""

    def __init__(
        self,
        config: GraphConfig,
        registry: SchemaRegistry | None = None,
        pool_factory: PoolFactory | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or SchemaRegistry()
        self._connection_pool = GraphConnectionPool(config, pool_factory=pool_factory)
        self._executor = QueryExecutor(self._connection_pool, config)
        self.vertices = VertexOperations(self._executor, self._registry)
        self.edges = EdgeOperations(self._executor, self._registry)
        self.traversal = Traversal(self._executor)
        self.metadata = Metadata(self._executor)

    def connect(self) -> None:
        self._connection_pool.start()

    def close(self) -> None:
        self._connection_pool.close()

    def execute_raw(self, ngql: str) -> QueryResult:
        """Escape hatch for operations not covered by the primitives above."""
        return self._executor.execute(ngql)

    def __enter__(self) -> "GraphClient":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
```

Also update `src/graph_core/__init__.py`:

```python
"""graph-core: a domain-agnostic Graph Data Layer over NebulaGraph."""

from graph_core.client import GraphClient

__all__ = ["GraphClient"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full unit test suite**

Run: `python3 -m pytest tests/unit -v`
Expected: PASS (all tests across all tasks, 0 failures)

- [ ] **Step 6: Commit**

```bash
git add src/graph_core/client.py src/graph_core/__init__.py tests/unit/test_client.py
git commit -m "feat: add GraphClient facade"
```

---

### Task 20: Integration test scaffolding and documentation

**Files:**
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_smoke.py`
- Create: `README.md`

**Interfaces:**
- Produces: integration tests skipped by default unless `NEBULA_TEST_HOST` is set; a top-level README documenting usage and the extension points.

- [ ] **Step 1: Create the integration test skip mechanism**

```python
# tests/integration/conftest.py
"""Integration tests require a real NebulaGraph instance.

They are skipped by default. Set NEBULA_TEST_HOST to a reachable
NebulaGraph graphd host to run them locally.
"""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("NEBULA_TEST_HOST"):
        return
    skip_integration = pytest.mark.skip(reason="Set NEBULA_TEST_HOST to run integration tests")
    for item in items:
        item.add_marker(skip_integration)
```

- [ ] **Step 2: Create a smoke test for later use against a real instance**

```python
# tests/integration/test_smoke.py
"""Run this against a real NebulaGraph instance once nebula3-python is
installed: set NEBULA_TEST_HOST=<host> NEBULA_TEST_PORT=<port> and run
`pytest tests/integration -v`.

Verify in particular:
- GraphClient.connect()/close() succeed against the real ConnectionPool.
- The exact nebula3-python method names assumed in
  storage/serialization.py (ValueWrapper.is_vertex()/as_node(),
  Node.tags()/properties(), Relationship.ranking(), etc.) match the
  installed client version — these were written from documented knowledge
  of the API and explicitly not verified against an installed copy.
"""

import os

import pytest

from graph_core.client import GraphClient
from graph_core.config import GraphConfig


@pytest.mark.integration
def test_connect_and_create_space_and_tag():
    config = GraphConfig(
        hosts=[(os.environ["NEBULA_TEST_HOST"], int(os.environ.get("NEBULA_TEST_PORT", 9669)))],
        user=os.environ.get("NEBULA_TEST_USER", "root"),
        password=os.environ.get("NEBULA_TEST_PASSWORD", "nebula"),
        space=os.environ.get("NEBULA_TEST_SPACE", "graph_core_smoke_test"),
    )
    with GraphClient(config) as client:
        assert client.metadata.list_spaces() is not None
```

- [ ] **Step 3: Verify integration tests are skipped by default**

Run: `python3 -m pytest tests/integration -v`
Expected: 1 test, SKIPPED (reason: "Set NEBULA_TEST_HOST to run integration tests")

- [ ] **Step 4: Write the README**

```markdown
# graph-core

A domain-agnostic Graph Data Layer over NebulaGraph. See
`docs/specs/2026-07-02-graph-core-design.md` for the full
architecture and design rationale.

## Installation

    pip install -e ".[dev]"

## Running tests

Unit tests require no NebulaGraph instance or installed `nebula3-python`:

    pytest tests/unit -v

Integration tests require a real NebulaGraph instance and the
`nebula3-python` package installed. They are skipped unless `NEBULA_TEST_HOST`
is set:

    NEBULA_TEST_HOST=127.0.0.1 pytest tests/integration -v

## Usage

    from graph_core import GraphClient
    from graph_core.config import GraphConfig

    config = GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user="root",
        password="nebula",
        space="my_space",
    )

    with GraphClient(config) as client:
        client.metadata.create_space("my_space")
        # ... create tags/edges, then use client.vertices / client.edges / client.traversal

## Extending with a new domain (e.g. a future AML package)

1. Subclass `graph_core.model.vertex.Vertex` / `graph_core.model.edge.Edge`,
   optionally overriding `validate()`.
2. Call `SchemaRegistry.register_vertex("account", AccountVertex)` /
   `register_edge(...)` at import time.
3. Define `TagSchema`/`EdgeSchema` and call `Metadata.create_tag(...)` /
   `create_edge_type(...)` to materialize the schema in NebulaGraph.
4. Compose `VertexOperations`, `EdgeOperations`, `Traversal` inside your own
   domain-specific repository rather than inheriting from them.

No changes to `graph-core` itself are required to add a new domain.
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/conftest.py tests/integration/test_smoke.py README.md
git commit -m "docs: add integration test scaffolding and README"
```

---

## Plan Self-Review Notes

- **Spec coverage:** every component in the design doc's "Project Structure" and "Component Details" sections has a corresponding task (identifiers → Task 2, exceptions → 3, config → 4, model → 5/6, storage → 7–11, query → 12, schema → 13/14, metadata → 15, repository → 16–18, client → 19, testing/docs → 20).
- **Type consistency checked:** `Vertex.__init__(vid, properties)` (Task 5) matches the deserialization call in `VertexOperations._to_domain` (Task 16); `Edge.__init__(src, dst, rank, properties)` (Task 6) matches `EdgeOperations._to_domain` (Task 17); `QueryResult.rows: list[dict]` (Task 7) matches every consumer (`single_row()`, `Metadata`, `Traversal`, `VertexOperations`/`EdgeOperations`).
- **No placeholders:** every step contains complete, runnable code.
