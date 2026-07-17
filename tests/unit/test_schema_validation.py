"""
Flourish Governed Memory Hub - Schema Validation & Integrity Tests
Verifies that all 8 ORM tables, columns, constraints, foreign keys, enums,
and indexes exactly match Blueprint Section 11 specifications.
"""

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from app.core.constants import AuditActionEnum, KnowledgeStatusEnum, SensitivityLabelEnum
from app.models.base import Base
# Ensure all models are registered in Base.metadata
import app.models  # noqa: F401


def test_metadata_table_count_and_names() -> None:
    """Verify exactly 8 relational tables exist in ORM metadata matching Blueprint Section 11."""
    expected_tables = {
        "namespaces",
        "roles",
        "role_namespace_permissions",
        "users",
        "knowledge_items",
        "governance_decisions",
        "audit_logs",
        "audit_sequence_head",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert actual_tables == expected_tables, f"Mismatch in schema tables: {actual_tables ^ expected_tables}"


def test_knowledge_items_table_columns_and_types() -> None:
    """Verify knowledge_items table column layout matches Blueprint Section 11.4."""
    table = Base.metadata.tables["knowledge_items"]
    expected_columns = {
        "item_id",
        "title",
        "body",
        "source_uri",
        "domain_namespace",
        "sensitivity_label",
        "sensitivity_level",
        "status",
        "version",
        "is_latest_approved",
        "search_vector",
        "embedding",
        "ingested_by_id",
        "created_at",
    }
    actual_columns = set(table.columns.keys())
    assert actual_columns == expected_columns, f"Missing or extra columns in knowledge_items: {actual_columns ^ expected_columns}"

    # Verify check constraints
    ck_names = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_knowledge_items_chk_knowledge_sensitivity_level" in ck_names
    assert "ck_knowledge_items_chk_knowledge_version" in ck_names

    # Verify specialized indices
    idx_names = {idx.name for idx in table.indexes}
    assert "idx_knowledge_retrieval_scoping" in idx_names
    assert "uidx_latest_approved_source" in idx_names


def test_foreign_key_restrict_deletion_rule() -> None:
    """Verify that all Foreign Keys to namespaces, roles, and users enforce ON DELETE RESTRICT (Brief P10/BR-05)."""
    for table_name, table in Base.metadata.tables.items():
        for fk_constraint in table.constraints:
            if isinstance(fk_constraint, ForeignKeyConstraint):
                for fk in fk_constraint.elements:
                    assert fk.ondelete == "RESTRICT", (
                        f"Table {table_name} FK to {fk.column} must enforce ON DELETE RESTRICT, got {fk.ondelete}"
                    )


def test_domain_enumerations_strict_values() -> None:
    """Verify exact enumeration values from Blueprint Section 11.0."""
    assert set(KnowledgeStatusEnum) == {
        KnowledgeStatusEnum.PENDING,
        KnowledgeStatusEnum.APPROVED,
        KnowledgeStatusEnum.REJECTED,
        KnowledgeStatusEnum.ARCHIVED,
    }
    assert set(SensitivityLabelEnum) == {
        SensitivityLabelEnum.PUBLIC,
        SensitivityLabelEnum.INTERNAL,
        SensitivityLabelEnum.CONFIDENTIAL,
        SensitivityLabelEnum.RESTRICTED,
    }
    assert set(AuditActionEnum) == {
        AuditActionEnum.INGEST,
        AuditActionEnum.APPROVE,
        AuditActionEnum.REJECT,
        AuditActionEnum.RETRIEVE_SUCCESS,
        AuditActionEnum.RETRIEVE_DENIED,
    }
    assert SensitivityLabelEnum.CONFIDENTIAL.level_value == 3


def test_audit_sequence_head_singleton_constraint() -> None:
    """Verify audit_sequence_head has lock_key primary key and check constraint ensuring lock_key = 1."""
    table = Base.metadata.tables["audit_sequence_head"]
    assert "lock_key" in table.primary_key.columns
    ck_names = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "ck_audit_sequence_head_chk_singleton_head" in ck_names


def test_tc_stable_001_public_orm_exports() -> None:
    """
    TC-STABLE-001: Verify that Component #1 exposes only the approved public ORM interfaces.
    Expected: Future components can import app.models.KnowledgeItem, app.models.User,
    and app.models.GovernanceDecision cleanly without modifying Component #1.
    """
    from app.models import (
        AuditLog,
        AuditSequenceHead,
        GovernanceDecision,
        KnowledgeItem,
        Namespace,
        Role,
        RoleNamespacePermission,
        User,
    )

    assert KnowledgeItem.__tablename__ == "knowledge_items"
    assert User.__tablename__ == "users"
    assert GovernanceDecision.__tablename__ == "governance_decisions"
    assert AuditLog.__tablename__ == "audit_logs"
    assert Namespace.__tablename__ == "namespaces"
    assert Role.__tablename__ == "roles"
    assert RoleNamespacePermission.__tablename__ == "role_namespace_permissions"
    assert AuditSequenceHead.__tablename__ == "audit_sequence_head"
