"""
Pydantic DTO Schema Package (`Option A Decoupled API Boundaries`).
"""

from app.schemas.audit import VerifyLedgerResponse
from app.schemas.common import ErrorResponse, StatusResponse
from app.schemas.context import (
    AssembleContextRequest,
    AssembleContextResponse,
    ContextManifestEntry,
)
from app.schemas.governance import AdjudicateItemRequest, AdjudicateItemResponse
from app.schemas.ingestion import IngestItemRequest, IngestItemResponse
from app.schemas.retrieval import GetItemResponse, SearchHitResponse, SearchRequest

__all__ = [
    "ErrorResponse",
    "StatusResponse",
    "IngestItemRequest",
    "IngestItemResponse",
    "AdjudicateItemRequest",
    "AdjudicateItemResponse",
    "SearchRequest",
    "SearchHitResponse",
    "GetItemResponse",
    "AssembleContextRequest",
    "AssembleContextResponse",
    "ContextManifestEntry",
    "VerifyLedgerResponse",
]
