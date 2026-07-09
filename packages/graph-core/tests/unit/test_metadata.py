from graph_core.metadata import Metadata
from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema
from graph_core.storage.result import QueryResult


class FakeExecutor:
    def __init__(self):
        self.executed = []
        self.use_space_flags = []
        self.responses = {}

    def execute(self, ngql, use_space=True):
        self.executed.append(ngql)
        self.use_space_flags.append(use_space)
        return self.responses.get(ngql, QueryResult(column_names=[], rows=[]))


def test_create_space_issues_create_space_statement_without_use():
    executor = FakeExecutor()
    Metadata(executor).create_space("aml")
    assert executor.executed == ['CREATE SPACE IF NOT EXISTS aml(vid_type=FIXED_STRING(32))']
    assert executor.use_space_flags == [False]


def test_drop_space_issues_drop_space_statement_without_use():
    executor = FakeExecutor()
    Metadata(executor).drop_space("aml")
    assert executor.executed == ["DROP SPACE IF EXISTS aml"]
    assert executor.use_space_flags == [False]


def test_list_spaces_extracts_names_without_use():
    executor = FakeExecutor()
    executor.responses["SHOW SPACES"] = QueryResult(
        column_names=["Name"], rows=[{"Name": "aml"}, {"Name": "test_space"}]
    )
    names = Metadata(executor).list_spaces()
    assert names == ["aml", "test_space"]
    assert executor.use_space_flags == [False]


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
