"""
Flourish Governed Memory Hub - Clearance & Identity ORM Models
Matches exactly with Blueprint Sections 11.1, 11.2, & 11.3:
- namespaces
- roles
- role_namespace_permissions
- users
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.audit import AuditLog
    from app.models.governance import GovernanceDecision
    from app.models.knowledge import KnowledgeItem


class Namespace(Base):
    """
    Represents organizational departments/domains (`eng.core`, `hr.layoffs`).
    Mandated by Blueprint Section 11.1 (L1010).
    """

    __tablename__ = "namespaces"

    namespace_id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    permissions: Mapped[list["RoleNamespacePermission"]] = relationship(
        "RoleNamespacePermission", back_populates="namespace"
    )
    knowledge_items: Mapped[list["KnowledgeItem"]] = relationship(
        "KnowledgeItem", back_populates="namespace_rel"
    )


class Role(Base):
    """
    Represents functional clearance roles (`ENGINEER`, `STEWARD`, `ADMIN`).
    Mandated by Blueprint Section 11.2 (L1019).
    """

    __tablename__ = "roles"

    role_id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    permissions: Mapped[list["RoleNamespacePermission"]] = relationship(
        "RoleNamespacePermission", back_populates="role"
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="role_rel")


class RoleNamespacePermission(Base):
    """
    3NF/BCNF junction matrix defining maximum sensitivity accessible per role per namespace.
    Mandated by Blueprint Section 11.3 (L1025).
    """

    __tablename__ = "role_namespace_permissions"
    __table_args__ = (
        CheckConstraint("max_sensitivity_level BETWEEN 1 AND 4", name="chk_permission_sensitivity"),
    )

    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("roles.role_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    namespace_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("namespaces.namespace_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    max_sensitivity_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
    namespace: Mapped["Namespace"] = relationship("Namespace", back_populates="permissions")


class User(Base):
    """
    Represents human actors and automated service accounts.
    Mandated by Blueprint Section 11.3 (L1034) & Brief P10/P13.
    """

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    identity_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    functional_role: Mapped[str] = mapped_column(
        String(50), ForeignKey("roles.role_id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Relationships
    role_rel: Mapped["Role"] = relationship("Role", back_populates="users")
    ingested_items: Mapped[list["KnowledgeItem"]] = relationship(
        "KnowledgeItem", back_populates="ingested_by_user"
    )
    governance_decisions: Mapped[list["GovernanceDecision"]] = relationship(
        "GovernanceDecision", back_populates="steward_user"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor_user")
