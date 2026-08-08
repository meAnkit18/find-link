"""Person-to-person network projection.

The graph is stored bipartite-ish: a person's phone, email, passport,
address, employer and so on are separate vertices hanging off the person by
a HAS_*/LOCATED_AT/WORKS_AT edge. So two people who share a phone are two
hops apart in storage, with no person->person edge between them at all.

An investigator does not think in storage hops — they think "who is this
person connected to, and why". This service projects the stored graph onto
a person-only graph where an edge means "these two share something", and
carries the shared thing along as the edge's reason. Degree 1/2/3 is then
breadth-first search over that projection, not over raw hops.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, NamedTuple

from graph_core.client import GraphClient
from graph_core.storage.result import RawEdge, RawVertex
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.services.connection_confidence import (
    BRIDGE_CONFIDENCE,
    DIRECT_CONFIDENCE,
    combine,
    match_confidence,
)
from graph_explorer_api.services.entity_props import merged_properties

PERSON_TAG = "person"

# The field-value index: one vertex per distinct normalised value, joined to
# every person holding it. Two people on the same one agreed on a value.
FIELD_VALUE_TAG = "field_value"
FIELD_VALUE_EDGE = "HAS_FIELD_VALUE"

# What a person expands into on the canvas. Phone/email/account/vehicle are
# still ingested and still form links — they are simply not what an
# investigator opens a person to look at.
EXPANDABLE_TAGS: frozenset[str] = frozenset({"document"})

# Person->person in one stored edge: the relationship *is* the connection.
DIRECT_EDGES: tuple[str, ...] = (
    "RELATED_TO",
    "PAYS",
    "COMMUNICATED_WITH",
    "TRANSFERRED_TO",
)

# Person->X<-person: two people attached to the same X are connected, and X
# is the reason. WORKS_AT/OWNS are in here deliberately — a shared employer
# is a real lead, even though a company is a first-class entity elsewhere.
SHARED_EDGES: tuple[str, ...] = (
    "HAS_FIELD_VALUE",
    "HAS_PHONE",
    "HAS_EMAIL",
    "HAS_DOCUMENT",
    "HAS_ACCOUNT",
    "OWNS_VEHICLE",
    "LOCATED_AT",
    "WORKS_AT",
    "OWNS",
)

# Technically shared, useless as a lead: everyone in a country is "connected".
# Available on request via the `connectors` parameter, never on by default.
WEAK_EDGES: tuple[str, ...] = ("CITIZEN_OF",)

# person -> org -[one of these]- org <- person. Two people at *different*
# companies are connected when the companies themselves are (a payment, an
# ownership stake, ...) — the money-flow pattern, and the one thing a plain
# shared-attribute rule cannot see. The link is reported with the direction
# it is stored in, so "Nimbus pays Meridian" doesn't read backwards.
BRIDGE_EDGES: tuple[str, ...] = (
    "PAYS",
    "OWNS",
    "RELATED_TO",
    "TRANSFERRED_TO",
    "SHAREHOLDER_OF",
    "DIRECTOR_OF",
)

# Only these connector kinds may be bridged. Widening this (bank_account is
# the obvious next one — account-to-account transfers are the same pattern)
# is a one-line change, but every addition multiplies the pairs a single
# level can emit, so it wants a fan-out check alongside.
BRIDGE_TAGS: tuple[str, ...] = ("company", "organization")

DEFAULT_MAX_FANOUT = 25
DEFAULT_MAX_PERSONS = 300
MAX_DEGREE = 3

_FETCH_CHUNK = 200


class Connectors(NamedTuple):
    direct: tuple[str, ...]
    shared: tuple[str, ...]
    bridge: tuple[str, ...]


class PersonNetworkService:
    def __init__(self, clients: GraphClientCache, space: str) -> None:
        self._clients = clients
        self._space = space

    @property
    def client(self) -> GraphClient:
        """Resolve the current client so a drop/recreate cycle doesn't leave
        this service holding a closed connection pool."""
        return self._clients.for_space(self._space)

    # ------------------------------------------------------------ public API

    def person_network(
        self,
        root_id: str,
        degree: int = 1,
        connectors: list[str] | None = None,
        min_confidence: float = 0.0,
        max_fanout: int = DEFAULT_MAX_FANOUT,
        max_persons: int = DEFAULT_MAX_PERSONS,
    ) -> dict | None:
        """Persons within `degree` connections of `root_id`, and why.

        Returns None when the root doesn't exist or isn't a person — the
        router turns that into a 404.
        """
        degree = max(1, min(int(degree), MAX_DEGREE))
        edges = self._resolve_connectors(connectors)

        root = self._fetch_vertices([root_id]).get(root_id)
        if root is None or PERSON_TAG not in root.tags:
            return None

        persons: dict[str, dict] = {root_id: _person_payload(root, 0)}
        links: dict[tuple[str, str], dict] = {}
        suppressed: dict[str, dict] = {}
        truncated = False
        frontier = [root_id]

        for level in range(1, degree + 1):
            if not frontier:
                break
            found = self._expand_level(frontier, set(persons), edges, max_fanout)
            suppressed.update(found.suppressed_hubs)

            # Filtering before the frontier is built is what makes the
            # threshold cut the path rather than just hide one edge: a person
            # only reachable through a link too weak to show is not reachable.
            reachable: set[str] = set()
            for key, via in found.links.items():
                if _link_confidence(via) < min_confidence:
                    continue
                reachable.update(key)
                link = links.get(key)
                if link is None:
                    links[key] = {
                        "source": key[0],
                        "target": key[1],
                        "degree": level,
                        "via": list(via),
                    }
                else:
                    _merge_via(link["via"], via)

            next_frontier: list[str] = []
            for vid in sorted(found.persons):
                if vid in persons or vid not in reachable:
                    continue
                if len(persons) >= max_persons:
                    truncated = True
                    break
                persons[vid] = _person_payload(found.persons[vid], level)
                next_frontier.append(vid)
            frontier = next_frontier

        # A link whose far end was cut by max_persons would dangle, so links
        # are filtered against the persons that actually made it in.
        kept_links = [
            _finalize_link(link)
            for link in links.values()
            if link["source"] in persons and link["target"] in persons
        ]

        return {
            "root_id": root_id,
            "degree": degree,
            "min_confidence": min_confidence,
            "persons": sorted(persons.values(), key=lambda p: (p["degree"], p["label"])),
            "links": sorted(kept_links, key=lambda link: (link["degree"], link["source"])),
            "truncated": truncated,
            "suppressed_hubs": sorted(
                suppressed.values(), key=lambda hub: -hub["person_count"]
            ),
            "connectors": {
                "direct": list(edges.direct),
                "shared": list(edges.shared),
                "bridge": list(edges.bridge),
            },
        }

    def attributes(self, entity_id: str, connectors: list[str] | None = None) -> dict:
        """One person's own attribute vertices (phone, email, address, ...),
        each annotated with the other people who share it — that's what makes
        an expanded attribute readable as the reason for a link."""
        shared_edges = self._resolve_connectors(connectors).shared
        if not shared_edges:
            return {"entity_id": entity_id, "attributes": []}

        own_edges = self.client.traversal.neighbors_batch([entity_id], list(shared_edges), "both")
        candidate_ids = _endpoints(own_edges) - {entity_id}
        vertices = self._fetch_vertices(sorted(candidate_ids))
        connector_ids = [
            vid
            for vid, vertex in vertices.items()
            if PERSON_TAG not in vertex.tags and _primary_tag(vertex) in EXPANDABLE_TAGS
        ]

        edge_type_by_connector: dict[str, str] = {}
        for edge in own_edges:
            other = edge.dst if edge.src == entity_id else edge.src
            if other in vertices and PERSON_TAG not in vertices[other].tags:
                edge_type_by_connector.setdefault(other, edge.edge_type)

        shared_with = self._owners(connector_ids, list(shared_edges))

        attributes = []
        for vid in connector_ids:
            vertex = vertices[vid]
            others = sorted(shared_with.get(vid, set()) - {entity_id})
            attributes.append(
                {
                    "id": vid,
                    "tag": _primary_tag(vertex),
                    "label": _label_of(vertex, vid),
                    "edge_type": edge_type_by_connector.get(vid, ""),
                    "properties": _merged_properties(vertex),
                    "shared_with": others,
                }
            )
        attributes.sort(key=lambda a: (a["tag"], a["label"]))
        return {"entity_id": entity_id, "attributes": attributes}

    # ----------------------------------------------------------- internals

    def _resolve_connectors(self, connectors: list[str] | None) -> Connectors:
        """Split the requested edge types into direct/shared/bridge, keeping
        only those the space actually has.

        A space built from a partial import won't have every edge type, and
        `GO ... OVER <unknown>` is a hard nGQL error, not an empty result.
        """
        if connectors is None:
            requested = set(DIRECT_EDGES) | set(SHARED_EDGES) | set(BRIDGE_EDGES)
        else:
            requested = {c.strip().upper() for c in connectors if c.strip()}

        try:
            available = set(self.client.metadata.list_edges())
        except Exception:
            available = requested  # can't introspect — let the query decide

        usable = requested & available
        return Connectors(
            direct=tuple(e for e in DIRECT_EDGES if e in usable),
            shared=tuple(e for e in SHARED_EDGES + WEAK_EDGES if e in usable),
            bridge=tuple(e for e in BRIDGE_EDGES if e in usable),
        )

    def _expand_level(
        self,
        frontier: list[str],
        known_person_ids: set[str],
        edges: Connectors,
        max_fanout: int,
    ) -> _LevelResult:
        traversal = self.client.traversal
        frontier_set = set(frontier)
        direct_edges, shared_edges = edges.direct, edges.shared

        direct_raw = (
            traversal.neighbors_batch(frontier, list(direct_edges), "both")
            if direct_edges
            else []
        )
        shared_raw = (
            traversal.neighbors_batch(frontier, list(shared_edges), "both")
            if shared_edges
            else []
        )

        vertices = self._fetch_vertices(
            sorted(_endpoints(direct_raw + shared_raw) - frontier_set)
        )
        connector_ids = [
            vid for vid, vertex in vertices.items() if PERSON_TAG not in vertex.tags
        ]

        owners_edges = (
            traversal.neighbors_batch(connector_ids, list(shared_edges), "both")
            if connector_ids and shared_edges
            else []
        )
        vertices.update(
            self._fetch_vertices(
                sorted(
                    _endpoints(owners_edges)
                    - set(vertices)
                    - frontier_set
                    - known_person_ids
                )
            )
        )

        def is_person(vid: str) -> bool:
            if vid in frontier_set or vid in known_person_ids:
                return True
            vertex = vertices.get(vid)
            return vertex is not None and PERSON_TAG in vertex.tags

        result = _LevelResult()

        for edge in direct_raw:
            if edge.src == edge.dst:
                continue
            if not (is_person(edge.src) and is_person(edge.dst)):
                continue
            key = _pair(edge.src, edge.dst)
            relationship = str(edge.properties.get("relationship_type") or "").strip()
            result.links[key].append(
                {
                    "kind": "direct",
                    "edge_types": [edge.edge_type],
                    "label": relationship or _humanize(edge.edge_type),
                    "confidence": DIRECT_CONFIDENCE,
                }
            )
            for endpoint in (edge.src, edge.dst):
                if endpoint not in frontier_set and endpoint in vertices:
                    result.persons[endpoint] = vertices[endpoint]

        connector_set = set(connector_ids)
        owners: dict[str, set[str]] = defaultdict(set)
        owner_edge_types: dict[tuple[str, str], set[str]] = defaultdict(set)
        owner_field_keys: dict[tuple[str, str], set[str]] = defaultdict(set)
        owner_documents: dict[tuple[str, str], set[str]] = defaultdict(set)
        for edge in owners_edges:
            for connector, person in ((edge.src, edge.dst), (edge.dst, edge.src)):
                if connector in connector_set and is_person(person):
                    owners[connector].add(person)
                    owner_edge_types[(connector, person)].add(edge.edge_type)
                    if edge.edge_type == FIELD_VALUE_EDGE:
                        field_key = str(edge.properties.get("field_key") or "").strip()
                        if field_key:
                            owner_field_keys[(connector, person)].add(field_key)
                        document = str(edge.properties.get("document_id") or "").strip()
                        if document:
                            owner_documents[(connector, person)].add(document)

        for connector, connected in owners.items():
            vertex = vertices.get(connector)
            if vertex is None:
                continue
            if len(connected) > max_fanout:
                # A phone shared by 400 people is a call centre, not a lead —
                # and it would emit ~80k links. Report it rather than hide it.
                result.suppressed_hubs[connector] = {
                    "id": connector,
                    "label": _label_of(vertex, connector),
                    "tag": _primary_tag(vertex),
                    "person_count": len(connected),
                }
                continue
            if len(connected) < 2:
                continue  # an attribute of exactly one person links nobody

            members = sorted(connected)

            if _primary_tag(vertex) == FIELD_VALUE_TAG:
                # Unlike a shared phone, a matching value is scored per pair:
                # which field each side used decides whether this is a
                # same-key match or the weaker cross-key kind.
                for index, first in enumerate(members):
                    for second in members[index + 1 :]:
                        first_keys = owner_field_keys[(connector, first)]
                        second_keys = owner_field_keys[(connector, second)]
                        shared_keys = first_keys & second_keys
                        all_keys = sorted(first_keys | second_keys)
                        same_key = bool(shared_keys)
                        field_key = sorted(shared_keys)[0] if same_key else (
                            all_keys[0] if all_keys else ""
                        )
                        result.links[_pair(first, second)].append({
                            "kind": "shared_field",
                            "connector_id": connector,
                            "connector_tag": FIELD_VALUE_TAG,
                            "connector_label": _label_of(vertex, connector),
                            "field_key": field_key,
                            "field_keys": all_keys,
                            "same_key": same_key,
                            "edge_types": [FIELD_VALUE_EDGE],
                            # Which documents on each side stated the value,
                            # so the reason is auditable back to its source.
                            "document_ids": sorted(
                                owner_documents[(connector, first)]
                                | owner_documents[(connector, second)]
                            ),
                            "confidence": match_confidence(field_key, len(connected), same_key),
                        })
                for member in members:
                    if member not in frontier_set and member in vertices:
                        result.persons[member] = vertices[member]
                continue

            via = {
                "kind": "shared_attribute",
                "connector_id": connector,
                "connector_tag": _primary_tag(vertex),
                "connector_label": _label_of(vertex, connector),
                "edge_types": sorted(
                    {
                        edge_type
                        for member in members
                        for edge_type in owner_edge_types[(connector, member)]
                    }
                ),
                "confidence": match_confidence(
                    _primary_tag(vertex), len(connected), same_key=True
                ),
            }
            for index, first in enumerate(members):
                for second in members[index + 1 :]:
                    result.links[_pair(first, second)].append(dict(via))
            for member in members:
                if member not in frontier_set and member in vertices:
                    result.persons[member] = vertices[member]

        self._add_bridged_links(
            result, connector_ids, vertices, owners, edges, max_fanout, frontier_set, is_person
        )
        return result

    def _add_bridged_links(
        self,
        result: _LevelResult,
        connector_ids: list[str],
        vertices: dict[str, RawVertex],
        owners: dict[str, set[str]],
        edges: Connectors,
        max_fanout: int,
        frontier_set: set[str],
        is_person: Callable[[str], bool],
    ) -> None:
        """Connect people whose *different* organisations are related.

        Priya works at Meridian, Arjun at Nimbus, and Nimbus pays Meridian:
        they share nothing, yet they are plainly connected. A shared-vertex
        rule cannot see that, because the two connectors are different
        vertices — this walks the one extra hop between them.
        """
        if not edges.bridge or not edges.shared:
            return

        near = [
            vid
            for vid in connector_ids
            if _primary_tag(vertices[vid]) in BRIDGE_TAGS and owners.get(vid)
        ]
        if not near:
            return

        traversal = self.client.traversal
        bridge_raw = traversal.neighbors_batch(near, list(edges.bridge), "both")
        near_set = set(near)

        far_ids = sorted(_endpoints(bridge_raw) - near_set)
        vertices.update(self._fetch_vertices([v for v in far_ids if v not in vertices]))
        far_set = {
            vid
            for vid in far_ids
            if vid in vertices and _primary_tag(vertices[vid]) in BRIDGE_TAGS
        }
        if not far_set:
            return

        far_owner_edges = traversal.neighbors_batch(sorted(far_set), list(edges.shared), "both")
        vertices.update(
            self._fetch_vertices(
                [v for v in sorted(_endpoints(far_owner_edges)) if v not in vertices]
            )
        )
        far_owners: dict[str, set[str]] = defaultdict(set)
        for edge in far_owner_edges:
            for org, person in ((edge.src, edge.dst), (edge.dst, edge.src)):
                if org in far_set and is_person(person):
                    far_owners[org].add(person)

        for edge in bridge_raw:
            for this, other in ((edge.src, edge.dst), (edge.dst, edge.src)):
                if this not in near_set or other not in far_set:
                    continue
                here, there = owners.get(this, set()), far_owners.get(other, set())
                if not here or not there:
                    continue
                if len(here) > max_fanout or len(there) > max_fanout:
                    continue  # a hub org would pair everyone with everyone
                via = {
                    "kind": "linked_organisation",
                    "connector_id": this,
                    "connector_tag": _primary_tag(vertices[this]),
                    "connector_label": _label_of(vertices[this], this),
                    "linked_id": other,
                    "linked_tag": _primary_tag(vertices[other]),
                    "linked_label": _label_of(vertices[other], other),
                    "edge_types": [edge.edge_type],
                    "label": _bridge_label(edge, vertices),
                    "confidence": BRIDGE_CONFIDENCE,
                }
                for person in here:
                    for far_person in there:
                        if person == far_person:
                            continue
                        result.links[_pair(person, far_person)].append(dict(via))
                        for end in (person, far_person):
                            if end not in frontier_set and end in vertices:
                                result.persons[end] = vertices[end]

    def _owners(self, connector_ids: list[str], shared_edges: list[str]) -> dict[str, set[str]]:
        """connector vid -> the person vids attached to it."""
        if not connector_ids:
            return {}
        edges = self.client.traversal.neighbors_batch(connector_ids, shared_edges, "both")
        vertices = self._fetch_vertices(sorted(_endpoints(edges) - set(connector_ids)))
        connector_set = set(connector_ids)
        owners: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            for connector, person in ((edge.src, edge.dst), (edge.dst, edge.src)):
                if connector not in connector_set:
                    continue
                vertex = vertices.get(person)
                if vertex is not None and PERSON_TAG in vertex.tags:
                    owners[connector].add(person)
        return owners

    def _fetch_vertices(self, vids: list[str]) -> dict[str, RawVertex]:
        found: dict[str, RawVertex] = {}
        for start in range(0, len(vids), _FETCH_CHUNK):
            chunk = vids[start : start + _FETCH_CHUNK]
            if not chunk:
                continue
            for vertex in self.client.vertices.get_many_raw(chunk):
                found[vertex.vid] = vertex
        return found


class _LevelResult:
    def __init__(self) -> None:
        self.persons: dict[str, RawVertex] = {}
        self.links: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.suppressed_hubs: dict[str, dict] = {}


# --------------------------------------------------------------- helpers


def _pair(a: str, b: str) -> tuple[str, str]:
    """Undirected link key — the projection has no direction."""
    return (a, b) if a <= b else (b, a)


def _endpoints(edges) -> set[str]:
    ends: set[str] = set()
    for edge in edges:
        ends.add(edge.src)
        ends.add(edge.dst)
    return ends


def _primary_tag(vertex: RawVertex) -> str:
    return next(iter(vertex.tags), "entity")


def _merged_properties(vertex: RawVertex) -> dict:
    return merged_properties(vertex)


def _label_of(vertex: RawVertex, fallback: str) -> str:
    for props in vertex.tags.values():
        label = props.get("label")
        if isinstance(label, str) and label.strip():
            return label
    return fallback


def _person_payload(vertex: RawVertex, degree: int) -> dict:
    properties = _merged_properties(vertex)
    return {
        "id": vertex.vid,
        "label": _label_of(vertex, vertex.vid),
        "degree": degree,
        "entity_type": str(properties.get("entity_type") or "Person"),
        "properties": properties,
    }


def _humanize(edge_type: str) -> str:
    return edge_type.replace("_", " ").lower()


def _bridge_label(edge: RawEdge, vertices: dict[str, RawVertex]) -> str:
    """Read the bridge in the direction it is stored, so "Nimbus pays
    Meridian" doesn't come out backwards."""
    src = vertices.get(edge.src)
    dst = vertices.get(edge.dst)
    src_label = _label_of(src, edge.src) if src else edge.src
    dst_label = _label_of(dst, edge.dst) if dst else edge.dst
    return f"{src_label} {_humanize(edge.edge_type)} {dst_label}"


def _merge_via(existing: list[dict], incoming: list[dict]) -> None:
    """Same pair rediscovered at a later level — keep every distinct reason."""
    seen = {_via_key(v) for v in existing}
    for via in incoming:
        key = _via_key(via)
        if key not in seen:
            seen.add(key)
            existing.append(via)


def _via_key(via: dict) -> tuple:
    """Identity of a reason, independent of which end it was found from.

    A bridge discovered walking Priya->Meridian->Nimbus->Arjun and the same
    bridge rediscovered next level as Arjun->Nimbus->Meridian->Priya are one
    reason, not two, so the pair of connectors is sorted rather than ordered.
    """
    connectors = tuple(sorted(c for c in (via.get("connector_id"), via.get("linked_id")) if c))
    return (
        via.get("kind"),
        connectors,
        tuple(via.get("edge_types", [])),
        tuple(via.get("field_keys", [])),
    )


def _link_confidence(via: list[dict]) -> float:
    """Independent reasons compound — see connection_confidence.combine."""
    return combine(float(entry.get("confidence") or 0.0) for entry in via)


def _finalize_link(link: dict) -> dict:
    via = link["via"]
    if len(via) == 1:
        entry = via[0]
        if entry["kind"] == "shared_attribute":
            label = f"shared {_humanize(entry['connector_tag'])}"
        elif entry["kind"] == "shared_field":
            label = f"matching {_humanize(entry['field_key'] or 'field')}"
        else:
            # direct and linked_organisation both carry a ready sentence
            label = entry["label"]
    else:
        label = f"{len(via)} connections"
    return {**link, "label": label, "confidence": round(_link_confidence(via), 4)}
