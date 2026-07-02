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
