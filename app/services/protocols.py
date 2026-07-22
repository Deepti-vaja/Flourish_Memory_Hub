"""
Flourish Governed Memory Hub - Service Protocols (`Component #3`)
Defines the runtime checkable protocol contract for Blue-Green namespaced ingestion (`Section 26.3`).
Operates asynchronously over an open SQLAlchemy AsyncSession (`psycopg3`).
"""

from typing import Any, Protocol, runtime_checkable

from app.core.constants import SensitivityLabelEnum
from app.security.context import CallerContext


@runtime_checkable
class IngestionServiceProtocol(Protocol):
    """
    Contract for Blue-Green namespaced document ingestion (`Section 26.3`).
    Operates asynchronously over an open SQLAlchemy AsyncSession (`psycopg3`).
    """

    async def ingest_item(
        self,
        session: Any,
        caller: CallerContext,
        title: str,
        body: str,
        source_uri: str | None,
        domain_namespace: str,
        sensitivity_label: str | SensitivityLabelEnum,
        embedding: list[float] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrates Blue-Green ingestion, version increment, tsvector index generation,
        and atomic cryptographic audit logging. Returns the exact DTO representation of the ingested item.
        """
        ...


__all__ = ["IngestionServiceProtocol"]
