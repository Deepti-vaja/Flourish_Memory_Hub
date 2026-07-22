"""
Flourish Governed Memory Hub - Cryptographic Audit Ledger ORM Models
Matches exactly with Blueprint Sections 11.6 & 11.7 (L1121–L1145):
- audit_logs (append-only cryptographic hash chain table)
- audit_sequence_head (single-row concurrency lock & head pointer table)
"""

import datetime
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AuditActionEnum
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeItem
    from app.models.namespace import User


class AuditLog(Base):
    """
    Append-only cryptographic event ledger.
    Every read, write, and adjudication attempt appends a row whose `entry_hash`
    is mathematically linked to `prev_hash` via HMAC-SHA256.
    Mandated by Blueprint Section 11.6 (L1121) & Brief P13/P36.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_event_time", "event_time"),
        Index("idx_audit_actor_action", "actor_id", "action_type"),
    )

    sequence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    action_type: Mapped[AuditActionEnum] = mapped_column(
        SQLEnum(AuditActionEnum, name="audit_action_enum", create_type=False),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_items.item_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Relationships
    actor_user: Mapped["User"] = relationship("User", back_populates="audit_logs")
    target_item: Mapped["KnowledgeItem | None"] = relationship(
        "KnowledgeItem", back_populates="audit_logs"
    )


class AuditSequenceHead(Base):
    """
    Single-row serialization lock table (`SELECT ... FOR UPDATE WHERE lock_key = 1`).
    Provides $O(1)$ head hash retrieval and prevents sequence forks or deadlock under concurrency.
    Mandated by Blueprint Section 11.7 (L1139) & Section 19 (RSK-01).
    """

    __tablename__ = "audit_sequence_head"
    __table_args__ = (CheckConstraint("lock_key = 1", name="chk_singleton_head"),)

    lock_key: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_sequence_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)
