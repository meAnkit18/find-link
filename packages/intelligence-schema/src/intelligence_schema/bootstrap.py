from graph_core.metadata import Metadata
from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema
from graph_core.schema.registry import SchemaRegistry
from intelligence_schema.entities.address import AddressVertex
from intelligence_schema.entities.bank_account import BankAccountVertex
from intelligence_schema.entities.company import CompanyVertex
from intelligence_schema.entities.country import CountryVertex
from intelligence_schema.entities.crypto_wallet import CryptoWalletVertex
from intelligence_schema.entities.document import DocumentVertex
from intelligence_schema.entities.domain import DomainVertex
from intelligence_schema.entities.email import EmailVertex
from intelligence_schema.entities.ip_address import IPAddressVertex
from intelligence_schema.entities.person import PersonVertex
from intelligence_schema.entities.phone import PhoneVertex
from intelligence_schema.entities.sanction_entry import SanctionEntryVertex
from intelligence_schema.entities.transaction import TransactionVertex
from intelligence_schema.entities.watchlist_entry import WatchlistEntryVertex
from intelligence_schema.entities.website import WebsiteVertex
from intelligence_schema.relationships.communicated_with import CommunicatedWithEdge
from intelligence_schema.relationships.director_of import DirectorOfEdge
from intelligence_schema.relationships.linked_with import LinkedWithEdge
from intelligence_schema.relationships.lives_at import LivesAtEdge
from intelligence_schema.relationships.located_at import LocatedAtEdge
from intelligence_schema.relationships.owns import OwnsEdge
from intelligence_schema.relationships.registered_to import RegisteredToEdge
from intelligence_schema.relationships.related_to import RelatedToEdge
from intelligence_schema.relationships.shareholder_of import ShareholderOfEdge
from intelligence_schema.relationships.transferred_to import TransferredToEdge
from intelligence_schema.relationships.works_at import WorksAtEdge


def register_schema() -> None:
    """Register all vertex and edge classes with the global SchemaRegistry."""
    SchemaRegistry.register_vertex("person", PersonVertex)
    SchemaRegistry.register_vertex("company", CompanyVertex)
    SchemaRegistry.register_vertex("address", AddressVertex)
    SchemaRegistry.register_vertex("phone", PhoneVertex)
    SchemaRegistry.register_vertex("email", EmailVertex)
    SchemaRegistry.register_vertex("bank_account", BankAccountVertex)
    SchemaRegistry.register_vertex("transaction", TransactionVertex)
    SchemaRegistry.register_vertex("document", DocumentVertex)
    SchemaRegistry.register_vertex("country", CountryVertex)
    SchemaRegistry.register_vertex("website", WebsiteVertex)
    SchemaRegistry.register_vertex("domain", DomainVertex)
    SchemaRegistry.register_vertex("ip_address", IPAddressVertex)
    SchemaRegistry.register_vertex("crypto_wallet", CryptoWalletVertex)
    SchemaRegistry.register_vertex("sanction_entry", SanctionEntryVertex)
    SchemaRegistry.register_vertex("watchlist_entry", WatchlistEntryVertex)

    SchemaRegistry.register_edge("RELATED_TO", RelatedToEdge)
    SchemaRegistry.register_edge("WORKS_AT", WorksAtEdge)
    SchemaRegistry.register_edge("OWNS", OwnsEdge)
    SchemaRegistry.register_edge("DIRECTOR_OF", DirectorOfEdge)
    SchemaRegistry.register_edge("SHAREHOLDER_OF", ShareholderOfEdge)
    SchemaRegistry.register_edge("LIVES_AT", LivesAtEdge)
    SchemaRegistry.register_edge("TRANSFERRED_TO", TransferredToEdge)
    SchemaRegistry.register_edge("LINKED_WITH", LinkedWithEdge)
    SchemaRegistry.register_edge("COMMUNICATED_WITH", CommunicatedWithEdge)
    SchemaRegistry.register_edge("REGISTERED_TO", RegisteredToEdge)
    SchemaRegistry.register_edge("LOCATED_AT", LocatedAtEdge)


def apply_schema(metadata: Metadata) -> None:
    """Create all intelligence-domain tags, edge types, and indexes in NebulaGraph."""
    metadata.create_tag(
        TagSchema(
            name="person",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("full_name", "string"),
                PropertyDefinition("date_of_birth", "date", nullable=True),
                PropertyDefinition("nationality", "string", nullable=True),
                PropertyDefinition("passport_number", "string", nullable=True),
                PropertyDefinition("national_id", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("status", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
                PropertyDefinition("last_seen_at", "datetime", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="company",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("name", "string"),
                PropertyDefinition("registration_number", "string", nullable=True),
                PropertyDefinition("country", "string", nullable=True),
                PropertyDefinition("incorporation_date", "date", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("status", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
                PropertyDefinition("last_seen_at", "datetime", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="address",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("full_address", "string"),
                PropertyDefinition("city", "string", nullable=True),
                PropertyDefinition("country", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="phone",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("number", "string"),
                PropertyDefinition("type", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="email",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("address", "string"),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="bank_account",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("account_number", "string"),
                PropertyDefinition("bank_name", "string", nullable=True),
                PropertyDefinition("iban", "string", nullable=True),
                PropertyDefinition("swift", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="transaction",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("amount", "double"),
                PropertyDefinition("currency", "string", nullable=True),
                PropertyDefinition("transaction_date", "datetime", nullable=True),
                PropertyDefinition("description", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="document",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("title", "string"),
                PropertyDefinition("document_type", "string", nullable=True),
                PropertyDefinition("language", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="country",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("code", "string"),
                PropertyDefinition("name", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="website",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("url", "string"),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="domain",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("domain_name", "string"),
                PropertyDefinition("registrar", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="ip_address",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("ip", "string"),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="crypto_wallet",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("address", "string"),
                PropertyDefinition("blockchain", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="sanction_entry",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("sanction_list", "string"),
                PropertyDefinition("sanctioned_name", "string", nullable=True),
                PropertyDefinition("sanctioned_entity_type", "string", nullable=True),
                PropertyDefinition("program", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag(
        TagSchema(
            name="watchlist_entry",
            properties=[
                PropertyDefinition("label", "string"),
                PropertyDefinition("entity_type", "string"),
                PropertyDefinition("watchlist_name", "string"),
                PropertyDefinition("watchlisted_name", "string", nullable=True),
                PropertyDefinition("category", "string", nullable=True),
                PropertyDefinition("risk_score", "double", nullable=True),
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("created_at", "datetime", nullable=True),
                PropertyDefinition("updated_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="RELATED_TO",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("relationship_type", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
                PropertyDefinition("last_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="WORKS_AT",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("position", "string", nullable=True),
                PropertyDefinition("start_date", "date", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="OWNS",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("ownership_percentage", "double", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="DIRECTOR_OF",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("position", "string", nullable=True),
                PropertyDefinition("appointment_date", "date", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="SHAREHOLDER_OF",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("shares_count", "int", nullable=True),
                PropertyDefinition("share_class", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="LIVES_AT",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("residence_type", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="TRANSFERRED_TO",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("amount", "double", nullable=True),
                PropertyDefinition("currency", "string", nullable=True),
                PropertyDefinition("transaction_date", "datetime", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="LINKED_WITH",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("link_type", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="COMMUNICATED_WITH",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("channel", "string", nullable=True),
                PropertyDefinition("communication_date", "datetime", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="REGISTERED_TO",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("registration_type", "string", nullable=True),
                PropertyDefinition("registration_date", "date", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_edge_type(
        EdgeSchema(
            name="LOCATED_AT",
            properties=[
                PropertyDefinition("confidence", "double", nullable=True),
                PropertyDefinition("source", "string", nullable=True),
                PropertyDefinition("evidence_ids", "string", nullable=True),
                PropertyDefinition("location_type", "string", nullable=True),
                PropertyDefinition("first_seen_at", "datetime", nullable=True),
            ],
        )
    )

    metadata.create_tag_index("person_label_idx", "person", ["label(128)"])
    metadata.create_tag_index("company_name_idx", "company", ["name(128)"])
    metadata.create_tag_index("person_passport_idx", "person", ["passport_number(64)"])
    metadata.create_tag_index("person_national_id_idx", "person", ["national_id(64)"])
    metadata.create_tag_index("bank_account_number_idx", "bank_account", ["account_number(64)"])
    metadata.create_tag_index("email_address_idx", "email", ["address(64)"])
    metadata.create_tag_index("phone_number_idx", "phone", ["number(64)"])
    metadata.create_tag_index("domain_name_idx", "domain", ["domain_name(128)"])
    metadata.create_tag_index("ip_address_idx", "ip_address", ["ip(64)"])
