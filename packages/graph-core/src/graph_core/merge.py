from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MergePlan:
    source_entity_id: str
    target_entity_id: str
    merged_properties: dict
    redirect_edges: bool = True
    preserve_source_as_alias: bool = True
