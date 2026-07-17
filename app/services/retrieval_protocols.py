"""
Retrieval Service Protocol Definition (`Stage 5 Engine`).

Mandated by Blueprint Section 26.5 (RetrievalServiceProtocol) & Section 13.
Strictly decoupled from concrete implementation (`Option A Immutability`).
"""
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable
import uuid
from app.security.context import CallerContext


@runtime_checkable
class RetrievalServiceProtocol(Protocol):
    """
    Contract for Clearance-Scoped Semantic Retrieval and Vector Query Engine.
    
    All implementations must guarantee:
    1. Active-Only Quarantine Gating (`status = APPROVED AND is_latest_approved = True`).
    2. Zero-Trust Horizontal (`domain_namespace IN allowed_namespaces`) and Vertical (`sensitivity_level <= max_sensitivity_level`) clearance filtering.
    3. Flag-32 Cover Density Normalized Hybrid Scoring (`pgvector cosine + ts_rank_cd`).
    4. Cryptographic Read Audit Ledgering (`AuditChainService.log_event` with `AuditActionEnum.RETRIEVE_SUCCESS`).
    """

    async def search(
        self,
        session: Any,
        caller: CallerContext,
        query_text: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        limit: int = 10,
        offset: int = 0,
        similarity_threshold: float = 0.7,
        domain_namespaces: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute clearance-scoped hybrid semantic search.
        
        Args:
            session: Active AsyncSession within caller-owned transaction boundary.
            caller: Authenticated CallerContext identity with namespace/sensitivity clearances.
            query_text: Optional natural language string for lexical Cover Density ranking (`ts_rank_cd flag 32`).
            query_vector: Optional 1536-dimensional float vector for semantic similarity (`embedding <=> query_vector`).
            limit: Maximum items to return (`<= 100`).
            offset: Pagination offset (`>= 0`).
            similarity_threshold: Minimum vector similarity threshold (`0.0 to 1.0`).
            domain_namespaces: Optional subset of namespaces to query (`must be within caller.allowed_namespaces`).
            
        Returns:
            List of zero-copy DTO dictionaries representing matching active knowledge items.
        """
        ...

    async def get_item_by_id(
        self,
        session: Any,
        caller: CallerContext,
        item_id: Union[str, uuid.UUID],
    ) -> Dict[str, Any]:
        """
        Fetch a single approved knowledge item by exact ID under strict clearance gating.
        
        Args:
            session: Active AsyncSession within caller-owned transaction boundary.
            caller: Authenticated CallerContext identity.
            item_id: Target document UUID.
            
        Returns:
            Zero-copy DTO dictionary of the document if active and clearance-authorized.
        """
        ...
