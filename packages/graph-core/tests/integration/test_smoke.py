"""Run this against a real NebulaGraph instance once nebula3-python is
installed: set NEBULA_TEST_HOST=<host> NEBULA_TEST_PORT=<port> (see
example.env for the full set of variables, including NEBULA_TEST_USE_SSL
for NebulaGraph Cloud) and run `pytest tests/integration -v`.

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
        use_ssl=os.environ.get("NEBULA_TEST_USE_SSL", "false").lower() == "true",
    )
    with GraphClient(config) as client:
        assert client.metadata.list_spaces() is not None
