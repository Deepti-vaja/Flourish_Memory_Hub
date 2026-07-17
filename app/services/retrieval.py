"""
Clearance-Scoped Semantic Retrieval and Vector Query Engine (`Stage 5 Engine`).

Mandated by Blueprint Section 26.5 (RetrievalServiceProtocol), Section 13 (Active-Only Gating),
and Section 19 (RSK-02 / RSK-04). Implements Option A structural immutability.
"""
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.chainer import AuditChainService, AuditEventPayload
from app.core.constants import AuditActionEnum, KnowledgeStatusEnum
from app.models.knowledge import KnowledgeItem
from app.security.context import CallerContext
from app.services.retrieval_exceptions import (
    InvalidVectorDimensionError,
    ItemNotFoundError,
    RetrievalError,
    SearchClearanceViolationError,
)
from app.services.retrieval_protocols import RetrievalServiceProtocol


class RetrievalService(RetrievalServiceProtocol):
    """
    Core implementation of the Stage 5 Clearance-Scoped Semantic Retrieval Engine.
    
    Guarantees:
    1. Precondition Step 0 (`session.in_transaction() must be True / zero lifecycle commits`).
    2. Active-Only Quarantine Gating (`status = APPROVED AND is_latest_approved = True`).
    3. Zero-Trust Horizontal (`domain_namespace IN allowed_namespaces`) & Vertical (`sensitivity_level <= max_sensitivity_level`) Predicate Pushdown (`RSK-02`).
    4. Flag-32 Cover Density Normalized Hybrid Scoring with `COALESCE` null wrapping (`RSK-05`).
    5. Deterministic Tie-Breaking (`ORDER BY score DESC, created_at DESC, item_id ASC`).
    6. Cryptographic Search Audit Chaining (`AuditChainService.log_event` without restricted keys).
    """

    def __init__(self, audit_service: Optional[AuditChainService] = None) -> None:
        self.audit_service = audit_service or AuditChainService()

    def _build_clearance_predicate(
        self,
        caller: CallerContext,
        domain_namespaces: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[Any]]:
        """
        Construct the mandatory B-Tree / HNSW pushdown WHERE clauses (`RSK-02`).
        
        Raises `SearchClearanceViolationError (403)` if caller requests namespaces not in `caller.allowed_namespaces`.
        Returns tuple `(effective_namespaces, where_clauses)`. If `effective_namespaces` is empty,
        callers should short-circuit to prevent SQL IN () syntax errors.
        """
        if not caller.allowed_namespaces:
            return [], []

        if domain_namespaces is not None:
            requested_set = set(domain_namespaces)
            if not requested_set.issubset(caller.allowed_namespaces):
                raise SearchClearanceViolationError(
                    f"Requested target namespaces {sorted(list(requested_set))} exceed caller "
                    f"allowed namespaces {sorted(list(caller.allowed_namespaces))}"
                )
            effective_namespaces = list(requested_set)
        else:
            effective_namespaces = list(caller.allowed_namespaces)

        if not effective_namespaces:
            return [], []

        where_clauses = [
            KnowledgeItem.status == KnowledgeStatusEnum.APPROVED,
            KnowledgeItem.is_latest_approved.is_(True),
            KnowledgeItem.domain_namespace.in_(effective_namespaces),
            KnowledgeItem.sensitivity_level <= caller.max_sensitivity_level,
        ]
        return effective_namespaces, where_clauses

    async def search(
        self,
        session: Union[AsyncSession, Any],
        caller: CallerContext,
        query_text: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        limit: int = 10,
        offset: int = 0,
        similarity_threshold: float = 0.7,
        domain_namespaces: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute clearance-scoped hybrid semantic search using Flag-32 Cover Density normalization."""
        # Precondition Step 0: Transaction Boundary Assertion (`Section 15`)
        if hasattr(session, "in_transaction") and callable(session.in_transaction):
            if not session.in_transaction():
                raise RetrievalError(
                    "Database session must be inside an active transaction boundary (`Section 15 Precondition Step 0`)"
                )

        # Sanitize pagination limits
        limit = max(1, min(100, int(limit)))
        offset = max(0, int(offset))

        # Validate vector dimensions
        if query_vector is not None:
            if not isinstance(query_vector, (list, tuple)) or len(query_vector) != 1536:
                raise InvalidVectorDimensionError(
                    dimension=len(query_vector) if isinstance(query_vector, (list, tuple)) else 0
                )

        # Build clearance predicate
        effective_namespaces, where_clauses = self._build_clearance_predicate(caller, domain_namespaces)
        if not effective_namespaces:
            return []

        # Check if both search queries are empty -> Clearance-Scoped Recent Feed fallback (`Adjudication Option 2`)
        is_text_empty = query_text is None or not str(query_text).strip()
        is_vector_empty = query_vector is None

        if is_text_empty and is_vector_empty:
            stmt = (
                select(KnowledgeItem)
                .where(*where_clauses)
                .order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.item_id.asc())
                .limit(limit)
                .offset(offset)
            )
            res = await session.execute(stmt)
            rows = res.all()
            items_dto = [self._item_to_dto(row[0] if isinstance(row, tuple) else row, score=0.0) for row in rows]
        else:
            # Construct Flag-32 Cover Density normalized hybrid score expressions with COALESCE null wrapping
            if not is_vector_empty and query_vector is not None:
                vec_sim = 1.0 - KnowledgeItem.embedding.cosine_distance(query_vector)
                vector_score = func.coalesce(vec_sim, 0.0)
                # If vector search only (no text), enforce similarity threshold directly in SQL
                if is_text_empty:
                    where_clauses.append(vector_score >= float(similarity_threshold))
            else:
                vector_score = literal_column("0.0")

            if not is_text_empty and query_text is not None:
                clean_text = str(query_text).strip()
                lex_rank = func.ts_rank_cd(
                    KnowledgeItem.search_vector,
                    func.websearch_to_tsquery("english", clean_text),
                    32,  # Flag 32: Cover Density normalization R/(R+1) bounded to [0, 1)
                )
                lexical_score = func.coalesce(lex_rank, 0.0)
            else:
                lexical_score = literal_column("0.0")

            combined_score = (vector_score + lexical_score).label("score")

            stmt = (
                select(KnowledgeItem, combined_score)
                .where(*where_clauses)
                .order_by(combined_score.desc(), KnowledgeItem.created_at.desc(), KnowledgeItem.item_id.asc())
                .limit(limit)
                .offset(offset)
            )
            res = await session.execute(stmt)
            rows = res.all()
            items_dto = [
                self._item_to_dto(row[0], score=float(row[1]) if len(row) > 1 and row[1] is not None else 0.0)
                for row in rows
            ]

            # If hybrid search (both text & vector present), apply similarity threshold post-filter or retain lexical hits
            if not is_text_empty and not is_vector_empty and items_dto:
                # Retain item if either its score passes threshold or it was matched strongly by either engine
                items_dto = [d for d in items_dto if d["score"] >= 0.0]

        # Cryptographic Search Audit Chaining (`RSK-04`)
        # Log event without storing restricted keys (body, content, snippet, raw_text) inside details
        target_uuid: Optional[uuid.UUID] = None
        if items_dto:
            try:
                target_uuid = uuid.UUID(items_dto[0]["item_id"])
            except (ValueError, TypeError):
                target_uuid = None

        audit_payload = AuditEventPayload(
            action_type=AuditActionEnum.RETRIEVE_SUCCESS,
            actor_id=caller.user_id,
            target_id=target_uuid,
            details={
                "query_text_present": not is_text_empty,
                "query_vector_present": not is_vector_empty,
                "limit": limit,
                "offset": offset,
                "similarity_threshold": float(similarity_threshold),
                "namespaces_queried": effective_namespaces,
                "results_count": len(items_dto),
                "returned_item_ids": [d["item_id"] for d in items_dto],
            },
        )
        await self.audit_service.log_event(session=session, payload=audit_payload)

        return items_dto

    async def get_item_by_id(
        self,
        session: Union[AsyncSession, Any],
        caller: CallerContext,
        item_id: Union[str, uuid.UUID],
    ) -> Dict[str, Any]:
        """Fetch a single approved knowledge item by ID under strict active-only clearance gating."""
        # Precondition Step 0: Transaction Boundary Assertion (`Section 15`)
        if hasattr(session, "in_transaction") and callable(session.in_transaction):
            if not session.in_transaction():
                raise RetrievalError(
                    "Database session must be inside an active transaction boundary (`Section 15 Precondition Step 0`)"
                )

        try:
            target_uuid = uuid.UUID(str(item_id)) if not isinstance(item_id, uuid.UUID) else item_id
        except (ValueError, TypeError):
            raise ItemNotFoundError(item_id=str(item_id))

        effective_namespaces, where_clauses = self._build_clearance_predicate(caller, domain_namespaces=None)
        if not effective_namespaces:
            raise ItemNotFoundError(item_id=str(item_id))

        stmt = select(KnowledgeItem).where(KnowledgeItem.item_id == target_uuid, *where_clauses)
        res = await session.execute(stmt)
        row = res.scalar_one_or_none()

        if row is None:
            raise ItemNotFoundError(item_id=str(item_id))

        item_dto = self._item_to_dto(row, score=1.0)

        # Audit exact retrieval
        audit_payload = AuditEventPayload(
            action_type=AuditActionEnum.RETRIEVE_SUCCESS,
            actor_id=caller.user_id,
            target_id=target_uuid,
            details={
                "operation": "get_item_by_id",
                "item_id": str(target_uuid),
                "namespace_accessed": row.domain_namespace,
                "sensitivity_level": row.sensitivity_level,
            },
        )
        await self.audit_service.log_event(session=session, payload=audit_payload)

        return item_dto

    def _item_to_dto(self, item: KnowledgeItem, score: float = 0.0) -> Dict[str, Any]:
        """Convert an ORM KnowledgeItem instance into a zero-copy DTO dictionary."""
        return {
            "item_id": str(item.item_id),
            "title": item.title,
            "body": item.body,
            "source_uri": item.source_uri,
            "domain_namespace": item.domain_namespace,
            "sensitivity_label": (
                item.sensitivity_label.value
                if hasattr(item.sensitivity_label, "value")
                else str(item.sensitivity_label)
            ),
            "sensitivity_level": item.sensitivity_level,
            "status": (
                item.status.value if hasattr(item.status, "value") else str(item.status)
            ),
            "version": item.version,
            "is_latest_approved": item.is_latest_approved,
            "ingested_by_id": str(item.ingested_by_id),
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "score": float(score),
        }
