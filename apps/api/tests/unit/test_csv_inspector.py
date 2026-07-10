import pytest

from graph_explorer_api.ingest.csv_inspector import inspect_csv


def test_infers_column_types(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text("name,age,active\nAlice,30,true\nBob,40,false\nCara,,true\n")

    result = inspect_csv(str(path))

    by_name = {c.name: c for c in result.columns}
    assert by_name["name"].inferred_type == "string"
    assert by_name["age"].inferred_type == "int"
    assert by_name["active"].inferred_type == "bool"
    assert by_name["age"].null_ratio == pytest.approx(1 / 3)


def test_infers_float_when_mixed_with_decimals(tmp_path):
    path = tmp_path / "scores.csv"
    path.write_text("id,score\n1,3.5\n2,4\n3,5.25\n")

    result = inspect_csv(str(path))
    by_name = {c.name: c for c in result.columns}
    assert by_name["score"].inferred_type == "float"


def test_sniffs_semicolon_delimiter(tmp_path):
    path = tmp_path / "semi.csv"
    path.write_text("a;b;c\n1;2;3\n4;5;6\n")

    result = inspect_csv(str(path))
    assert result.delimiter == ";"
    assert result.headers == ["a", "b", "c"]
