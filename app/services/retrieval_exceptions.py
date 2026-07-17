"""
Domain Exception Hierarchy for Component #5 (`Retrieval Engine — Stage 5 Engine`).

All retrieval exceptions inherit from `FlourishGovernanceError` (Component #2 Base Exception),
ensuring uniform trapping, mapping, and HTTP status code translation by Stage 7 routers (`Section 14`).
"""
from typing import Optional
from app.services.exceptions import FlourishGovernanceError


class RetrievalError(FlourishGovernanceError):
    """Base exception for all semantic retrieval engine failures (500 Internal Server Error)."""

    def __init__(self, message: str = "Semantic retrieval operation failed"):
        super().__init__(message)
        self.error_code = "RETRIEVAL_ERROR"
        self.message = message


class SearchClearanceViolationError(RetrievalError):
    """
    Raised when requested search parameters exceed caller horizontal or vertical security clearance (403 Forbidden).
    """

    def __init__(self, message: str = "Search request exceeds caller security clearance boundaries"):
        super().__init__(message)
        self.error_code = "SEARCH_CLEARANCE_VIOLATION"


class InvalidVectorDimensionError(RetrievalError):
    """
    Raised when query_vector does not exactly match the mandated 1536 dimensions (400 Bad Request).
    """

    def __init__(self, dimension: int):
        message = f"Invalid query_vector dimension: {dimension}. Expected exactly 1536 dimensions."
        super().__init__(message)
        self.error_code = "INVALID_VECTOR_DIMENSION"
        self.dimension = dimension


class ItemNotFoundError(RetrievalError):
    """
    Raised when target document does not exist, is quarantined (PENDING/REJECTED), or is outside caller clearance (404 Not Found).
    """

    def __init__(self, item_id: str):
        message = f"Knowledge item not found or not authorized for retrieval: '{item_id}'"
        super().__init__(message)
        self.error_code = "ITEM_NOT_FOUND"
        self.item_id = item_id
