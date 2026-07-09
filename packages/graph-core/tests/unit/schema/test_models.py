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
