"""A small demo population for the document-sourced person graph.

Every person here exists to exercise one behaviour of the projection, so a
canvas loaded from this dataset shows each case side by side:

  chain        Amina -> Yusuf -> Khalid -> Sofia, one hop per matching field,
               so degree 1/2/3 visibly widens the net.
  compounding  Amina and Yusuf match on *two* fields, so their link scores
               higher than either field alone would give.
  cross-key    Omar's passport `address` equals Lina's Emirates ID
               `residence_address` — a real match, scored lower than a
               same-key one.
  shared doc   Two customer files on one passport: the duplicate-identity
               case, scored near-conclusive.
  noise        Six people born in Dubai. A real match, worth almost nothing,
               and the thing the confidence filter exists to remove.
  denylist     Everyone is a UAE national — and that must connect nobody.
  control      Clara matches no one. Most customers look like this.

Pure data: no graph, no I/O. `seed_demo_graph.py` writes it into
NebulaGraph and `test_demo_seed.py` runs the same plan through the
in-memory fake store, so both agree on what the dataset means.
"""

from __future__ import annotations

from intelligence_schema.field_index import field_values

# Everyone is a UAE national and every document names its issuer. Both keys
# are denylisted, so neither may produce a single link — the dataset would
# otherwise be one fully-connected blob.
COMMON = {"nationality": "United Arab Emirates", "issuing_country": "United Arab Emirates"}

PEOPLE: list[dict] = [
    {"id": "demo_p_amina_rahman", "name": "Amina Rahman",
     "attributes": {"dob": "1988-03-11", **COMMON}},
    {"id": "demo_p_yusuf_rahman", "name": "Yusuf Rahman",
     "attributes": {"dob": "1991-07-02", **COMMON}},
    {"id": "demo_p_khalid_nasser", "name": "Khalid Nasser",
     "attributes": {"dob": "1985-01-24", **COMMON}},
    {"id": "demo_p_sofia_castro", "name": "Sofia Castro",
     "attributes": {"dob": "1990-11-09", **COMMON}},
    {"id": "demo_p_omar_haddad", "name": "Omar Haddad",
     "attributes": {"dob": "1979-05-30", **COMMON}},
    {"id": "demo_p_lina_farouk", "name": "Lina Farouk",
     "attributes": {"dob": "1993-09-17", **COMMON}},
    {"id": "demo_p_mohammed_iqbal", "name": "Mohammed Iqbal",
     "attributes": {"dob": "1982-02-14", **COMMON}},
    {"id": "demo_p_mohamed_ikbal", "name": "Mohamed Ikbal",
     "attributes": {"dob": "1982-02-14", **COMMON}},
    {"id": "demo_p_clara_dubois", "name": "Clara Dubois",
     "attributes": {"dob": "1995-06-21", **COMMON}},
]

# The Dubai-born crowd: a match nobody should act on. Amina is one of them,
# so the noise attaches to a person who also has real links — which is what
# makes raising the confidence filter visibly useful rather than academic.
_CROWD = ["Rami Aziz", "Noor Salim", "Tariq Bilal", "Hana Youssef", "Zaid Mansour"]
PEOPLE += [
    {"id": f"demo_p_{name.split()[0].lower()}_{name.split()[1].lower()}", "name": name,
     "attributes": {"dob": f"197{i}-04-0{i + 1}", **COMMON}}
    for i, name in enumerate(_CROWD)
]

DOCUMENTS: list[dict] = [
    # --- siblings: two fields agree, so the link compounds ----------------
    {"id": "demo_doc_amina_pp", "holder": "demo_p_amina_rahman",
     "document_type": "passport", "number": "A1122334",
     "attributes": {"father_name": "Ibrahim Rahman", "mother_name": "Fatima Rahman",
                    "place_of_birth": "Dubai", "expiry_date": "2030-03-11"}},
    {"id": "demo_doc_yusuf_pp", "holder": "demo_p_yusuf_rahman",
     "document_type": "passport", "number": "A5566778",
     "attributes": {"father_name": "Ibrahim Rahman", "mother_name": "Fatima Rahman",
                    "place_of_birth": "Sharjah", "expiry_date": "2029-07-02"}},

    # --- one hop on: Yusuf and Khalid share a home address ----------------
    {"id": "demo_doc_yusuf_eid", "holder": "demo_p_yusuf_rahman",
     "document_type": "emirates_id", "number": "784-1991-7654321-2",
     "attributes": {"address": "12 Al Wasl Road, Dubai"}},
    {"id": "demo_doc_khalid_eid", "holder": "demo_p_khalid_nasser",
     "document_type": "emirates_id", "number": "784-1985-1234567-3",
     "attributes": {"address": "12 Al Wasl Road, Dubai",
                    "emergency_contact": "Ravi Menon"}},

    # --- and one more: Khalid and Sofia name the same contact ------------
    {"id": "demo_doc_sofia_pp", "holder": "demo_p_sofia_castro",
     "document_type": "passport", "number": "B9087654",
     "attributes": {"emergency_contact": "Ravi Menon", "place_of_birth": "Manila"}},

    # --- cross-key: same value, different field on each side -------------
    {"id": "demo_doc_omar_pp", "holder": "demo_p_omar_haddad",
     "document_type": "passport", "number": "C4433221",
     "attributes": {"address": "88 Marina Walk, Dubai"}},
    {"id": "demo_doc_lina_eid", "holder": "demo_p_lina_farouk",
     "document_type": "emirates_id", "number": "784-1993-9988776-1",
     "attributes": {"residence_address": "88 Marina Walk, Dubai"}},

    # --- the control: nothing Clara carries matches anyone ---------------
    {"id": "demo_doc_clara_pp", "holder": "demo_p_clara_dubois",
     "document_type": "passport", "number": "D1010101",
     "attributes": {"father_name": "Henri Dubois", "place_of_birth": "Lyon"}},
]

# Two customer files, one passport: the duplicate-identity case. This is a
# *shared document vertex*, not a field match — a different claim, and the
# strongest one the graph can make.
SHARED_DOCUMENT = {
    "id": "demo_doc_duplicate_pp", "document_type": "passport", "number": "E7654321",
    "holders": ["demo_p_mohammed_iqbal", "demo_p_mohamed_ikbal"],
    "attributes": {"father_name": "Abdul Iqbal", "place_of_birth": "Karachi"},
}

# Amina joins the crowd, so one person carries both a strong link and a
# worthless one.
_DUBAI_BORN = ["demo_p_amina_rahman"] + [p["id"] for p in PEOPLE[-len(_CROWD):]]


def _crowd_documents() -> list[dict]:
    """A passport per crowd member, agreeing only on place of birth."""
    return [
        {"id": f"demo_doc_crowd_{i}", "holder": person_id,
         "document_type": "passport", "number": f"F000{i}111",
         "attributes": {"place_of_birth": "Dubai"}}
        for i, person_id in enumerate(_DUBAI_BORN[1:], start=1)
    ]


def all_documents() -> list[dict]:
    """Every single-holder document, including the crowd's."""
    return DOCUMENTS + _crowd_documents()


def holdings() -> list[tuple[str, str]]:
    """(person_id, document_id) for every document, shared ones included."""
    pairs = [(doc["holder"], doc["id"]) for doc in all_documents()]
    pairs += [(holder, SHARED_DOCUMENT["id"]) for holder in SHARED_DOCUMENT["holders"]]
    return pairs


def document_by_id() -> dict[str, dict]:
    found = {doc["id"]: doc for doc in all_documents()}
    found[SHARED_DOCUMENT["id"]] = SHARED_DOCUMENT
    return found


def index_entries() -> list[tuple[str, str, str, str, str]]:
    """(person_id, field_key, normalised value, document_id, document_type).

    Exactly what ingestion would index: a person's own fields plus the
    fields of every document they hold. Derived through `field_index` rather
    than written out by hand, so the denylist and normalisation rules that
    apply in production apply here too.
    """
    docs = document_by_id()
    entries: list[tuple[str, str, str, str, str]] = []

    # A person's display name is not indexed, matching ingestion: the writer
    # is handed `reg.attributes`, and the canonical name is not in it.
    for person in PEOPLE:
        for key, value in field_values(person["attributes"]):
            entries.append((person["id"], key, value, "", ""))

    for person_id, document_id in holdings():
        document = docs[document_id]
        props = {**document["attributes"], "number": document["number"]}
        for key, value in field_values(props):
            entries.append(
                (person_id, key, value, document_id, document["document_type"])
            )

    return entries
