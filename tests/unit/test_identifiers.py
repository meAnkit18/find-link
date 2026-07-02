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
