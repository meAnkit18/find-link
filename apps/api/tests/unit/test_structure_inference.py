from graph_explorer_api.import_pipeline.csv_inspector import inspect_csv
from graph_explorer_api.import_pipeline.structure_inference import (
    EdgeListStructure,
    NodeTableStructure,
    infer_structure,
)


def test_detects_edge_list_via_header_names(tmp_path):
    path = tmp_path / "calls.csv"
    path.write_text(
        "source,target,relationship,since\n"
        "Alice,Bob,friend,2020\n"
        "Bob,Cara,coworker,2021\n"
        "Alice,Cara,friend,2019\n"
    )
    inspection = inspect_csv(str(path))
    structure = infer_structure(inspection, "calls")

    assert isinstance(structure, EdgeListStructure)
    assert structure.source_column == "source"
    assert structure.target_column == "target"
    assert structure.type_column == "relationship"
    assert "since" in structure.property_columns


def test_detects_node_table_when_no_pair_found(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text("id,name,age\n1,Alice,30\n2,Bob,40\n3,Cara,50\n4,Dan,25\n")
    inspection = inspect_csv(str(path))
    structure = infer_structure(inspection, "people")

    assert isinstance(structure, NodeTableStructure)
    assert structure.id_column == "id"
    assert structure.tag == "people"
    assert set(structure.property_columns) == {"name", "age"}


def test_edge_list_derives_node_tag_from_common_header_prefix(tmp_path):
    path = tmp_path / "friends.csv"
    path.write_text(
        "person_a,person_b\n"
        "Alice,Bob\nBob,Cara\nAlice,Cara\nBob,Dan\nAlice,Dan\n"
    )
    inspection = inspect_csv(str(path))
    structure = infer_structure(inspection, "friends")

    assert isinstance(structure, EdgeListStructure)
    assert {structure.source_column, structure.target_column} == {"person_a", "person_b"}
    assert structure.node_tag == "person"
