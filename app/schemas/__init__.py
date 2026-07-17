"""
Pydantic DTO Schema Package (`Option A Decoupled API Boundaries`).
"""
from app.schemas.common import ErrorResponse, StatusResponse
from app.schemas.ingestion import IngestItemRequest, IngestItemResponse
from app.schemas.governance import AdjudicateItemRequest, AdjudicateItemResponse
from app.schemas.retrieval import SearchRequest, SearchHitResponse, GetItemResponse
from app.schemas.context import AssembleContextRequest, AssembleContextResponse, ContextManifestEntry
from app.schemas.audit import VerifyLedgerResponse

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
    "VerifyLedgerResponse"
]
