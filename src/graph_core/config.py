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
