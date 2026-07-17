"""
Flourish Governed Memory Hub - Knowledge Repository ORM Model
Matches exactly with Blueprint Section 11.4 (L1043–L1102):
- knowledge_items table
- tsvector full-text search column (`search_vector`)
- pgvector semantic embedding column (`embedding`)
- partial unique index (`uidx_latest_approved_source`)
- composite scoping index (`idx_knowledge_retrieval_scoping`)
"""

import datetime
import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.core.constants import KnowledgeStatusEnum, SensitivityLabelEnum
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.namespace import Namespace, User
    from app.models.governance import GovernanceDecision
    from app.models.audit import AuditLog


class KnowledgeItem(Base):
    """
    Primary organizational knowledge repository table.
    Mandated by Blueprint Section 11.4 (L1043) & Brief P6/P12.
    """
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint("sensitivity_level BETWEEN 1 AND 4", name="chk_knowledge_sensitivity_level"),
        CheckConstraint("version >= 1", name="chk_knowledge_version"),
        # Partial unique index ensuring only one latest approved version per source_uri exists (RSK-05)
        Index(
            "uidx_latest_approved_source",
            "source_uri",
            unique=True,
            postgresql_where=text("is_latest_approved = TRUE AND status = 'APPROVED'"),
        ),
        # Composite B-Tree index for instantaneous Predicate Pushdown scoping (RSK-02)
        Index(
            "idx_knowledge_retrieval_scoping",
            "status",
            "domain_namespace",
            "sensitivity_level",
            "is_latest_approved",
        ),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    domain_namespace: Mapped[str] = mapped_column(
        String(100), ForeignKey("namespaces.namespace_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sensitivity_label: Mapped[SensitivityLabelEnum] = mapped_column(
        SQLEnum(SensitivityLabelEnum, name="sensitivity_label_enum", create_type=False),
        nullable=False,
        default=SensitivityLabelEnum.INTERNAL,
    )
    sensitivity_level: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[KnowledgeStatusEnum] = mapped_column(
        SQLEnum(KnowledgeStatusEnum, name="knowledge_status_enum", create_type=False),
        nullable=False,
        default=KnowledgeStatusEnum.PENDING,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Full-Text Search tsvector (GIN index created via Alembic script)
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)

    # Semantic Vector Embedding - statically locked to 1536 dimensions (HNSW index created via Alembic script)
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    ingested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    namespace_rel: Mapped["Namespace"] = relationship("Namespace", back_populates="knowledge_items")
    ingested_by_user: Mapped["User"] = relationship("User", back_populates="ingested_items")
    governance_decisions: Mapped[list["GovernanceDecision"]] = relationship(
        "GovernanceDecision", back_populates="item", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="target_item"
    )
