"""
Flourish Governed Memory Hub - Governance Service Protocols (`Component #4`)
Defines the runtime checkable protocol contract for Stage 4 Governance Adjudication (`Section 26.4`).
Operates asynchronously over an open SQLAlchemy AsyncSession (`psycopg3`).
Created as an independent module (`Option A Zero Modifications`) to preserve Component #3 immutability.
"""

from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable
from uuid import UUID
from app.security.context import CallerContext


@runtime_checkable
class GovernanceServiceProtocol(Protocol):
    """
    Contract for Stage 4 Governance Adjudication Core Engine (`Section 26.4`).
    All methods operate asynchronously over an open SQLAlchemy AsyncSession inside an active transaction (`session.begin()`).
    """
    async def adjudicate_item(
        self,
        session: Any,
        caller: CallerContext,
        item_id: Union[str, UUID],
        decision: str,  # 'APPROVED' or 'REJECTED'
        justification: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Orchestrates Stage 4 Domain Steward adjudication (`Section 12`).
        Enforces clearance checks, Four-Eyes Principle (`BR-05`), Blue-Green demotion (`RSK-05`),
        immutable governance decision persistence (`Section 11.5`), and cryptographic audit chaining (`RSK-04`).
        Returns the exact AdjudicationResultDTO (`Dict[str, Any]`).
        """
        ...

    async def list_pending_items(
        self,
        session: Any,
        caller: CallerContext,
        domain_namespace: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves quarantined (`PENDING`) knowledge items scoped strictly to the caller's
        horizontal (`allowed_namespaces`) and vertical (`max_sensitivity_level`) clearances (`Section 26.4`).
        Returns a list of PendingItemDTO (`Dict[str, Any]`).
        """
        ...


__all__ = ["GovernanceServiceProtocol"]
