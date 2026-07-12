"""Orchestrates one CSV import: inspect -> infer structure -> materialize
schema -> dedupe + bulk write -> report.

Runs synchronously; graph_explorer_api.ingest.jobs is what makes this
non-blocking for the API (runs it on a background thread).
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from graph_core.client import GraphClient
from graph_explorer_api.ingest import writer
from graph_explorer_api.ingest.csv_inspector import inspect_csv
from graph_explorer_api.ingest.report import ImportReport
from graph_explorer_api.ingest.structure_inference import (
    EdgeListStructure,
    NodeTableStructure,
    infer_structure,
)
from graph_explorer_api.naming import sanitize_identifier


def _coerce_row_properties(row: dict, columns, errors: list[str], row_number: int) -> dict:
    properties = {}
    for col in columns:
        raw = (row.get(col.name) or "").strip()
        value, ok = writer.coerce_value(raw, col.inferred_type)
        if not ok:
            errors.append(
                f"row {row_number}: could not parse {col.name!r}={row.get(col.name)!r} "
                f"as {col.inferred_type}, stored as null"
            )
        properties[col.name] = value
    return properties


def _run_node_table(
    client: GraphClient, structure: NodeTableStructure, columns_by_name, rows, report: ImportReport
) -> None:
    report.tag = structure.tag
    prop_columns = [columns_by_name[name] for name in structure.property_columns]
    writer.ensure_tag(client, structure.tag, prop_columns)
    label_column = writer.pick_label_column(
        [columns_by_name[n] for n in structure.property_columns], structure.property_columns
    )

    vertex_rows: list[tuple[str, dict]] = []
    for i, row in enumerate(rows):
        vid = (row.get(structure.id_column) or "").strip()
        if not vid:
            report.validation_errors.append(f"row {i + 2}: missing {structure.id_column!r}, skipped")
            continue
        properties = _coerce_row_properties(row, prop_columns, report.validation_errors, i + 2)
        raw_label = (row.get(label_column) or "").strip() if label_column else ""
        properties[writer.LABEL_PROPERTY] = raw_label or vid
        vertex_rows.append((vid, properties))

    created, duplicates = writer.write_vertices(client, structure.tag, vertex_rows)
    report.vertices_created = created
    report.duplicates_skipped += duplicates


def _run_edge_list(
    client: GraphClient, structure: EdgeListStructure, columns_by_name, rows, report: ImportReport
) -> None:
    report.tag = structure.node_tag
    report.edge_type = structure.default_edge_type
    prop_columns = [columns_by_name[name] for name in structure.property_columns]
    writer.ensure_tag(client, structure.node_tag, [])  # endpoints carry only a label

    vertex_rows: list[tuple[str, dict]] = []
    edges_by_type: dict[str, list[tuple[str, str, int, dict]]] = {}

    for i, row in enumerate(rows):
        row_number = i + 2
        src = (row.get(structure.source_column) or "").strip()
        dst = (row.get(structure.target_column) or "").strip()
        if not src or not dst:
            report.validation_errors.append(f"row {row_number}: missing endpoint, skipped")
            continue

        vertex_rows.append((src, {writer.LABEL_PROPERTY: src}))
        vertex_rows.append((dst, {writer.LABEL_PROPERTY: dst}))

        edge_type = structure.default_edge_type
        if structure.type_column:
            raw_type = (row.get(structure.type_column) or "").strip()
            if raw_type:
                edge_type = sanitize_identifier(raw_type, structure.default_edge_type).upper()

        properties = _coerce_row_properties(row, prop_columns, report.validation_errors, row_number)
        edges_by_type.setdefault(edge_type, []).append((src, dst, 0, properties))

    created_v, dup_v = writer.write_vertices(client, structure.node_tag, vertex_rows)
    report.vertices_created = created_v
    report.duplicates_skipped += dup_v

    for edge_type, edge_rows in edges_by_type.items():
        writer.ensure_edge_type(client, edge_type, prop_columns)
        created_e, dup_e = writer.write_edges(client, edge_type, edge_rows)
        report.edges_created += created_e
        report.duplicates_skipped += dup_e


def run_import(client: GraphClient, path: Path, filename: str) -> ImportReport:
    started = time.monotonic()
    inspection = inspect_csv(str(path))
    structure = infer_structure(inspection, Path(filename).stem)
    columns_by_name = {c.name: c for c in inspection.columns}

    report = ImportReport(filename=filename, structure_kind=structure.kind)

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=inspection.delimiter))
    report.rows_read = len(rows)

    if isinstance(structure, NodeTableStructure):
        _run_node_table(client, structure, columns_by_name, rows, report)
    else:
        _run_edge_list(client, structure, columns_by_name, rows, report)

    report.elapsed_seconds = time.monotonic() - started
    return report
