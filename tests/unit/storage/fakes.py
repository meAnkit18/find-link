"""Test doubles standing in for nebula3-python's wire-level types.

Method names here must match nebula3.data.DataObject's ValueWrapper/Node/
Relationship/PathWrapper API. Verify against the installed nebula3-python
version during integration testing.
"""


class FakeValueWrapper:
    def __init__(
        self,
        *,
        null=False,
        bool_=None,
        int_=None,
        double_=None,
        string_=None,
        list_=None,
        map_=None,
        vertex=None,
        edge=None,
        path=None,
    ):
        self._null = null
        self._bool = bool_
        self._int = int_
        self._double = double_
        self._string = string_
        self._list = list_
        self._map = map_
        self._vertex = vertex
        self._edge = edge
        self._path = path

    def is_null(self):
        return self._null

    def is_bool(self):
        return self._bool is not None

    def as_bool(self):
        return self._bool

    def is_int(self):
        return self._int is not None

    def as_int(self):
        return self._int

    def is_double(self):
        return self._double is not None

    def as_double(self):
        return self._double

    def is_string(self):
        return self._string is not None

    def as_string(self):
        return self._string

    def is_time(self):
        return False

    def is_date(self):
        return False

    def is_datetime(self):
        return False

    def is_list(self):
        return self._list is not None

    def as_list(self):
        return self._list

    def is_set(self):
        return False

    def is_map(self):
        return self._map is not None

    def as_map(self):
        return self._map

    def is_vertex(self):
        return self._vertex is not None

    def as_node(self):
        return self._vertex

    def is_edge(self):
        return self._edge is not None

    def as_relationship(self):
        return self._edge

    def is_path(self):
        return self._path is not None

    def as_path(self):
        return self._path


class FakeNode:
    def __init__(self, vid, tags):
        self._vid = vid
        self._tags = tags

    def get_id(self):
        return FakeValueWrapper(string_=self._vid)

    def tags(self):
        return list(self._tags.keys())

    def properties(self, tag_name):
        return self._tags[tag_name]


class FakeRelationship:
    def __init__(self, src, dst, edge_type, rank, properties):
        self._src = src
        self._dst = dst
        self._edge_type = edge_type
        self._rank = rank
        self._properties = properties

    def start_vertex_id(self):
        return FakeValueWrapper(string_=self._src)

    def end_vertex_id(self):
        return FakeValueWrapper(string_=self._dst)

    def edge_name(self):
        return self._edge_type

    def ranking(self):
        return self._rank

    def properties(self):
        return self._properties


class FakePath:
    def __init__(self, nodes, relationships):
        self._nodes = nodes
        self._relationships = relationships

    def nodes(self):
        return self._nodes

    def relationships(self):
        return self._relationships
