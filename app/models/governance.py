"""
Flourish Governed Memory Hub - Governance Adjudication ORM Model
Matches exactly with Blueprint Section 11.5 (L1105–L1119):
- governance_decisions table
Note: The Four-Eyes Principle trigger (`trg_governance_four_eyes`) checking that
`steward_id != knowledge_items.ingested_by_id` is created explicitly inside Alembic DDL.
"""

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeItem
    from app.models.namespace import User


class GovernanceDecision(Base):
    """
    Immutable audit history of adjudication decisions made by Domain Stewards.
    Mandated by Blueprint Section 11.5 (L1105) & Brief P10 (BR-05).
    """

    __tablename__ = "governance_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_items.item_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    steward_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'APPROVED' or 'REJECTED'
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )

    # Relationships
    item: Mapped["KnowledgeItem"] = relationship(
        "KnowledgeItem", back_populates="governance_decisions"
    )
    steward_user: Mapped["User"] = relationship("User", back_populates="governance_decisions")
