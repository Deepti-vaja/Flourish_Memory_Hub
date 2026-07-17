"""Initial Schema DDL Migration for Flourish Governed Memory Hub (`Stage 1`)

Revision ID: 2026_07_16_initial_schema
Revises:
Create Date: 2026-07-16 12:00:00.000000

"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = "2026_07_16_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable required PostgreSQL C extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create custom ENUM types (Blueprint Section 11.0)
    knowledge_status_enum = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", "ARCHIVED", name="knowledge_status_enum", create_type=False
    )
    knowledge_status_enum.create(op.get_bind(), checkfirst=True)

    sensitivity_label_enum = postgresql.ENUM(
        "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", name="sensitivity_label_enum", create_type=False
    )
    sensitivity_label_enum.create(op.get_bind(), checkfirst=True)

    audit_action_enum = postgresql.ENUM(
        "INGEST", "APPROVE", "REJECT", "RETRIEVE_SUCCESS", "RETRIEVE_DENIED", name="audit_action_enum", create_type=False
    )
    audit_action_enum.create(op.get_bind(), checkfirst=True)

    # 3. Create core identity and clearance tables (Blueprint Sections 11.1 - 11.3)
    op.create_table(
        "namespaces",
        sa.Column("namespace_id", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("namespace_id", name=op.f("pk_namespaces")),
    )
    op.create_index(op.f("ix_namespaces_namespace_id"), "namespaces", ["namespace_id"], unique=False)

    op.create_table(
        "roles",
        sa.Column("role_id", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("role_id", name=op.f("pk_roles")),
    )
    op.create_index(op.f("ix_roles_role_id"), "roles", ["role_id"], unique=False)

    op.create_table(
        "role_namespace_permissions",
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", sa.String(length=50), nullable=False),
        sa.Column("namespace_id", sa.String(length=100), nullable=False),
        sa.Column("max_sensitivity_level", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("max_sensitivity_level BETWEEN 1 AND 4", name=op.f("ck_role_namespace_permissions_chk_permission_sensitivity")),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.namespace_id"], name=op.f("fk_role_namespace_permissions_namespace_id_namespaces"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"], name=op.f("fk_role_namespace_permissions_role_id_roles"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("permission_id", name=op.f("pk_role_namespace_permissions")),
    )
    op.create_index(op.f("ix_role_namespace_permissions_namespace_id"), "role_namespace_permissions", ["namespace_id"], unique=False)
    op.create_index(op.f("ix_role_namespace_permissions_role_id"), "role_namespace_permissions", ["role_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_key", sa.String(length=255), nullable=False),
        sa.Column("functional_role", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["functional_role"], ["roles.role_id"], name=op.f("fk_users_functional_role_roles"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users")),
        sa.UniqueConstraint("identity_key", name=op.f("uq_users_identity_key")),
    )
    op.create_index(op.f("ix_users_functional_role"), "users", ["functional_role"], unique=False)
    op.create_index(op.f("ix_users_identity_key"), "users", ["identity_key"], unique=True)

    # 4. Create knowledge repository table & specialized indexes (Blueprint Section 11.4)
    op.create_table(
        "knowledge_items",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.String(length=512), nullable=True),
        sa.Column("domain_namespace", sa.String(length=100), nullable=False),
        sa.Column("sensitivity_label", sensitivity_label_enum, nullable=False, server_default="INTERNAL"),
        sa.Column("sensitivity_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", knowledge_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_latest_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        sa.Column("ingested_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("sensitivity_level BETWEEN 1 AND 4", name=op.f("ck_knowledge_items_chk_knowledge_sensitivity_level")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_knowledge_items_chk_knowledge_version")),
        sa.ForeignKeyConstraint(["domain_namespace"], ["namespaces.namespace_id"], name=op.f("fk_knowledge_items_domain_namespace_namespaces"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingested_by_id"], ["users.user_id"], name=op.f("fk_knowledge_items_ingested_by_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_knowledge_items")),
    )
    op.create_index(op.f("ix_knowledge_items_domain_namespace"), "knowledge_items", ["domain_namespace"], unique=False)
    op.create_index(op.f("ix_knowledge_items_ingested_by_id"), "knowledge_items", ["ingested_by_id"], unique=False)
    op.create_index(op.f("ix_knowledge_items_source_uri"), "knowledge_items", ["source_uri"], unique=False)
    op.create_index(op.f("ix_knowledge_items_status"), "knowledge_items", ["status"], unique=False)

    # Specialized Indexes mandated by Blueprint Section 11.4
    op.create_index("idx_knowledge_fts", "knowledge_items", ["search_vector"], postgresql_using="gin")
    op.create_index("idx_knowledge_retrieval_scoping", "knowledge_items", ["status", "domain_namespace", "sensitivity_level", "is_latest_approved"])
    op.create_index("uidx_latest_approved_source", "knowledge_items", ["source_uri"], unique=True, postgresql_where=sa.text("is_latest_approved = TRUE AND status = 'APPROVED'"))
    op.execute("CREATE INDEX idx_knowledge_vector ON knowledge_items USING hnsw (embedding vector_cosine_ops);")

    # 5. Create governance decisions table & Four-Eyes separation trigger (Blueprint Section 11.5)
    op.create_table(
        "governance_decisions",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("steward_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_type", sa.String(length=50), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_items.item_id"], name=op.f("fk_governance_decisions_item_id_knowledge_items"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["steward_id"], ["users.user_id"], name=op.f("fk_governance_decisions_steward_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("decision_id", name=op.f("pk_governance_decisions")),
    )
    op.create_index(op.f("ix_governance_decisions_item_id"), "governance_decisions", ["item_id"], unique=False)
    op.create_index(op.f("ix_governance_decisions_steward_id"), "governance_decisions", ["steward_id"], unique=False)

    # Create explicit PostgreSQL trigger function for Four-Eyes Principle (BR-05)
    op.execute("""
    CREATE OR REPLACE FUNCTION check_four_eyes_separation()
    RETURNS TRIGGER AS $$
    DECLARE
        v_ingested_by UUID;
    BEGIN
        SELECT ingested_by_id INTO v_ingested_by
        FROM knowledge_items
        WHERE item_id = NEW.item_id;
        
        IF NEW.steward_id = v_ingested_by THEN
            RAISE EXCEPTION 'Four-Eyes Principle Violation (BR-05): Steward (%) cannot approve an item they ingested themselves (%)', NEW.steward_id, v_ingested_by
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_governance_four_eyes
    BEFORE INSERT OR UPDATE ON governance_decisions
    FOR EACH ROW EXECUTE FUNCTION check_four_eyes_separation();
    """)

    # 6. Create cryptographic audit ledger table (Blueprint Section 11.6)
    op.create_table(
        "audit_logs",
        sa.Column("sequence_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("action_type", audit_action_enum, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.user_id"], name=op.f("fk_audit_logs_actor_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_id"], ["knowledge_items.item_id"], name=op.f("fk_audit_logs_target_id_knowledge_items"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("sequence_id", name=op.f("pk_audit_logs")),
        sa.UniqueConstraint("entry_hash", name=op.f("uq_audit_logs_entry_hash")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index("idx_audit_actor_action", "audit_logs", ["actor_id", "action_type"], unique=False)
    op.create_index("idx_audit_event_time", "audit_logs", ["event_time"], unique=False)
    op.create_index(op.f("ix_audit_logs_entry_hash"), "audit_logs", ["entry_hash"], unique=True)
    op.create_index(op.f("ix_audit_logs_target_id"), "audit_logs", ["target_id"], unique=False)

    # 7. Create audit sequence head lock table & singleton row (Blueprint Section 11.7)
    op.create_table(
        "audit_sequence_head",
        sa.Column("lock_key", sa.Integer(), nullable=False),
        sa.Column("last_sequence_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_entry_hash", sa.String(length=64), nullable=False, server_default="0000000000000000000000000000000000000000000000000000000000000000"),
        sa.CheckConstraint("lock_key = 1", name=op.f("ck_audit_sequence_head_chk_singleton_head")),
        sa.PrimaryKeyConstraint("lock_key", name=op.f("pk_audit_sequence_head")),
    )
    op.execute("INSERT INTO audit_sequence_head (lock_key, last_sequence_id, last_entry_hash) VALUES (1, 0, '0000000000000000000000000000000000000000000000000000000000000000') ON CONFLICT DO NOTHING;")


def downgrade() -> None:
    # Drop in reverse order of dependencies
    op.drop_table("audit_sequence_head")
    op.drop_table("audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_governance_four_eyes ON governance_decisions;")
    op.execute("DROP FUNCTION IF EXISTS check_four_eyes_separation();")
    op.drop_table("governance_decisions")
    op.drop_table("knowledge_items")
    op.drop_table("users")
    op.drop_table("role_namespace_permissions")
    op.drop_table("roles")
    op.drop_table("namespaces")

    # Drop custom ENUMs
    postgresql.ENUM(name="audit_action_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="sensitivity_label_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="knowledge_status_enum").drop(op.get_bind(), checkfirst=True)
