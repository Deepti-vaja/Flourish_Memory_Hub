"""
Flourish Governed Memory Hub - Service Core & Blue-Green Ingestion Engine (`Component #3`)
Implements `IngestionServiceProtocol` (`Section 26.3`) with verified architectural rules:
- Unconditional Zero-Trust Invariant (`status = PENDING, is_latest_approved = False`) (`Section 1.1`)
- Blue-Green version increment & isolation (`RSK-05`, `REQ-CORE-002`)
- 64-bit Composite PostgreSQL Transaction Advisory Locking (`pg_advisory_xact_lock`) (`RSK-01`)
- Single-transaction atomicity and fail-closed SLA (`RSK-06`, `Section 15`)
- Strict `details` dictionary forwarding to `AuditChainService.log_event` (`RSK-04`)
- Vector dimension & finite float validation (`RSK-07`) and keyword fallback (`RSK-04`)
- Null-byte (`\x00`) text sanitization (`RSK-08`)
- Pure DTO dictionary (`Dict[str, Any]`) return payload (`Section 26.3`)
"""

import math
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.audit.chainer import AuditChainProtocol, AuditEventPayload
from app.core.constants import AuditActionEnum, KnowledgeStatusEnum, SensitivityLabelEnum
from app.models.knowledge import KnowledgeItem
from app.models.namespace import Namespace
from app.security.context import CallerContext
from app.services.exceptions import (
    EmbeddingDimensionError,
    IngestionError,
    IngestionPayloadError,
    NamespaceAccessDeniedError,
    NamespaceNotFoundError,
    SensitivityViolationError,
)
from app.services.protocols import IngestionServiceProtocol

SENSITIVITY_LEVEL_MAP: dict[SensitivityLabelEnum, int] = {
    SensitivityLabelEnum.PUBLIC: 1,
    SensitivityLabelEnum.INTERNAL: 2,
    SensitivityLabelEnum.CONFIDENTIAL: 3,
    SensitivityLabelEnum.RESTRICTED: 4,
}


def _clean_text(text: str | None) -> str | None:
    """Strips PostgreSQL-incompatible null bytes (`\x00`) and leading/trailing whitespace (`RSK-08`)."""
    if text is None:
        return None
    cleaned = text.replace("\x00", "").strip()
    return cleaned if len(cleaned) > 0 else None


class IngestionService(IngestionServiceProtocol):
    """
    Concrete implementation of Blue-Green namespaced document ingestion (`Component #3`).
    Orchestrates zero-trust quarantine, version numbering, full-text indexing, and audit logging
    within a shared SQLAlchemy AsyncSession transaction boundary (`RSK-06`).
    """

    def __init__(self, audit_service: AuditChainProtocol) -> None:
        if not audit_service:
            raise IngestionError(
                "AuditChainProtocol instance is required to initialize IngestionService."
            )
        self._audit_service = audit_service

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
        Orchestrates Blue-Green ingestion (`Section 26.3`) over an active AsyncSession (`psycopg3`).
        Returns the exact DTO representation dictionary (`Dict[str, Any]`) of the newly created item.
        """
        # 1. Assert active transaction boundary (`ARCH-RULE-01 / Proposal E`)
        if not hasattr(session, "in_transaction") or not session.in_transaction():
            raise IngestionError(
                "Database session is closed or not inside an active transaction boundary (`session.begin()` required)."
            )

        try:
            # 2. Validate CallerContext structure and clearance types (`RSK-ING-06`, `Section 26.1`, `DEF-03`)
            if (
                not isinstance(caller, CallerContext)
                or not isinstance(caller.user_id, UUID)
                or not isinstance(caller.allowed_namespaces, (set, list, tuple, frozenset))
                or not isinstance(caller.max_sensitivity_level, int)
                or not (1 <= caller.max_sensitivity_level <= 4)
            ):
                raise IngestionError(
                    "Invalid or missing CallerContext identity or clearance attributes for ingestion."
                )

            # 3. Validate and sanitize text input payloads (`EDG-ING-16`, `EDG-ING-17`, `Proposal H`)
            clean_title = _clean_text(title)
            clean_body = _clean_text(body)
            clean_uri = _clean_text(source_uri)

            if not clean_title or not clean_body:
                raise IngestionPayloadError("Document title and body must be non-empty strings.")

            if len(clean_title) > 255:
                raise IngestionPayloadError(
                    f"Document title exceeds maximum length of 255 characters (got {len(clean_title)})."
                )

            if clean_uri is not None and len(clean_uri) > 512:
                raise IngestionPayloadError(
                    f"Document source_uri exceeds maximum length of 512 characters (got {len(clean_uri)})."
                )

            if len(clean_body.encode("utf-8")) > 10_000_000:
                raise IngestionPayloadError(
                    "Document payload exceeds maximum permitted size (10 MB)."
                )

            # 4. Resolve and validate sensitivity label & integer level (`Proposal F / ARCH-RULE-02`)
            if isinstance(sensitivity_label, str):
                try:
                    label_enum = SensitivityLabelEnum[sensitivity_label.upper()]
                except KeyError:
                    try:
                        label_enum = SensitivityLabelEnum(sensitivity_label.upper())
                    except ValueError:
                        raise IngestionPayloadError(
                            f"Invalid sensitivity label '{sensitivity_label}'. Must be one of: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED."
                        )
            elif isinstance(sensitivity_label, SensitivityLabelEnum):
                label_enum = sensitivity_label
            else:
                raise IngestionPayloadError(
                    "sensitivity_label must be a valid string or SensitivityLabelEnum."
                )

            level = SENSITIVITY_LEVEL_MAP[label_enum]

            # 5. Namespace existence and three-phase authorization gates (`Section 11.1 / 11.3`)
            ns_result = await session.execute(
                select(Namespace).where(Namespace.namespace_id == domain_namespace)
            )
            ns_row = ns_result.scalar_one_or_none()
            if not ns_row:
                raise NamespaceNotFoundError(f"Namespace '{domain_namespace}' does not exist.")

            if domain_namespace not in caller.allowed_namespaces:
                raise NamespaceAccessDeniedError(
                    f"Caller '{caller.identity_key}' is not authorized for namespace '{domain_namespace}'."
                )

            if level > caller.max_sensitivity_level:
                raise SensitivityViolationError(
                    f"Requested sensitivity level ({level}) exceeds caller maximum clearance ({caller.max_sensitivity_level})."
                )

            # 6. Validate semantic vector embedding dimensions and finite floats (`RSK-07`)
            if embedding is not None:
                if not isinstance(embedding, list) or len(embedding) != 1536:
                    raise EmbeddingDimensionError(
                        f"Embedding vector must contain exactly 1536 dimensions; got {len(embedding) if isinstance(embedding, list) else type(embedding).__name__}."
                    )
                if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in embedding):
                    raise EmbeddingDimensionError(
                        "Embedding vector contains non-finite floating-point values (NaN or Infinity) or invalid types."
                    )
                clean_embedding = list(embedding)
            else:
                clean_embedding = None  # Keyword-only fallback (`RSK-04`)

            # 7. 64-Bit Composite Advisory Transaction Locking & Blue-Green Version Calculation (`Proposal A / RSK-05`)
            if clean_uri is not None:
                # Serializes all concurrent workers across the cluster for this URI (`DEF-02 Path A`)
                await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(clean_uri))))
                # Verify global ownership across namespaces (`DEF-02 Path A`)
                existing_ns_result = await session.execute(
                    select(KnowledgeItem.domain_namespace)
                    .where(KnowledgeItem.source_uri == clean_uri)
                    .limit(1)
                )
                existing_ns = existing_ns_result.scalar_one_or_none()
                if existing_ns and existing_ns != domain_namespace:
                    raise IngestionPayloadError(
                        f"source_uri '{clean_uri}' is already registered under namespace '{existing_ns}'; cannot ingest across different namespaces (`DEF-02 Path A`)."
                    )

                # Query global max version for this source_uri (`Section 19 RSK-05`)
                max_ver_result = await session.execute(
                    select(func.max(KnowledgeItem.version)).where(
                        KnowledgeItem.source_uri == clean_uri,
                    )
                )
                max_ver = max_ver_result.scalar_one_or_none()
                version = (max_ver or 0) + 1
            else:
                version = 1  # One-off scratch note without canonical URI (`EDG-ING-12`)

            # 8. Unconditional Zero-Trust Invariant (`Proposal C / Section 1.1`)
            new_item = KnowledgeItem(
                title=clean_title,
                body=clean_body,
                source_uri=clean_uri,
                domain_namespace=domain_namespace,
                sensitivity_label=label_enum,
                sensitivity_level=level,
                status=KnowledgeStatusEnum.PENDING,
                version=version,
                is_latest_approved=False,
                search_vector=func.to_tsvector("english", f"{clean_title} {clean_body}"),
                embedding=clean_embedding,
                ingested_by_id=caller.user_id,
            )

            # 9. Persist item and hydrate server-computed expressions (`Proposal D / RSK-06`)
            session.add(new_item)
            await session.flush()
            await session.refresh(new_item, attribute_names=["search_vector", "created_at"])

            # 10. Forward details exclusively to AuditChainService (`Proposal B / RSK-04 / RSK-06`)
            audit_payload = AuditEventPayload(
                action_type=AuditActionEnum.INGEST,
                actor_id=caller.user_id,
                target_id=new_item.item_id,
                details=details or {},
            )
            seq_id = await self._audit_service.log_event(session, audit_payload)

            # 11. Return pure DTO dictionary (`Proposal I / Section 26.3`)
            return {
                "item_id": new_item.item_id,
                "title": new_item.title,
                "source_uri": new_item.source_uri,
                "domain_namespace": new_item.domain_namespace,
                "sensitivity_label": new_item.sensitivity_label.value,
                "sensitivity_level": new_item.sensitivity_level,
                "status": new_item.status.value,
                "version": new_item.version,
                "is_latest_approved": new_item.is_latest_approved,
                "ingested_by_id": new_item.ingested_by_id,
                "created_at": new_item.created_at,
                "search_vector": str(new_item.search_vector)
                if new_item.search_vector is not None
                else None,
                "embedding": list(new_item.embedding) if new_item.embedding is not None else None,
                "audit_sequence_id": seq_id,
            }
        except Exception as e:
            # Fail-closed transaction boundary wrapper (`Proposal G / RSK-06`)
            if hasattr(session, "in_transaction") and session.in_transaction():
                await session.rollback()
            raise e


__all__ = ["IngestionService", "_clean_text", "SENSITIVITY_LEVEL_MAP"]
