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
