"""
Stage 7 REST Controllers Package (`app/api/v1/endpoints`).
Exposes all Stage 1–6 domain features over ASGI/FastAPI without Option A mutations.
"""

from app.api.v1.endpoints.audit import router as audit_router
from app.api.v1.endpoints.context import router as context_router
from app.api.v1.endpoints.governance import router as governance_router
from app.api.v1.endpoints.ingestion import router as ingestion_router
from app.api.v1.endpoints.retrieval import router as retrieval_router

__all__ = [
    "ingestion_router",
    "governance_router",
    "retrieval_router",
    "context_router",
    "audit_router",
]
