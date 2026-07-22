"""
Aggregated Stage 7 API Router (`/api/v1`).
Includes ingestion, governance, retrieval, context assembly, and audit verification endpoints.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit_router,
    context_router,
    governance_router,
    ingestion_router,
    retrieval_router,
)

api_router = APIRouter()

api_router.include_router(ingestion_router, prefix="/ingestion", tags=["Stage 3 Ingestion"])
api_router.include_router(governance_router, prefix="/governance", tags=["Stage 4 Governance"])
api_router.include_router(retrieval_router, prefix="/retrieval", tags=["Stage 5 Retrieval"])
api_router.include_router(context_router, prefix="/context", tags=["Stage 6 Context Assembly"])
api_router.include_router(audit_router, prefix="/audit", tags=["Stage 2 Audit Ledger"])

__all__ = ["api_router"]
