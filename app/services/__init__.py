"""
Flourish Governed Memory Hub - Service Core & Blue-Green Ingestion Engine Package (`Component #3`)
Exports the public protocols, concrete services, and exception hierarchy.
"""

from app.services.exceptions import (
    EmbeddingDimensionError,
    IngestionError,
    IngestionPayloadError,
    NamespaceAccessDeniedError,
    NamespaceNotFoundError,
    SensitivityViolationError,
)
from app.services.ingestion import IngestionService
from app.services.protocols import IngestionServiceProtocol

__all__ = [
    "IngestionService",
    "IngestionServiceProtocol",
    "IngestionError",
    "NamespaceNotFoundError",
    "NamespaceAccessDeniedError",
    "SensitivityViolationError",
    "EmbeddingDimensionError",
    "IngestionPayloadError",
]
