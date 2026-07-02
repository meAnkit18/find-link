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
