"""
Flourish Governed Memory Hub - Service & Ingestion Exception Hierarchy (`Component #3`)
Defines the clean domain exception classes for Service Core & Blue-Green Ingestion (`Section 14`).
All exceptions strictly inherit from `FlourishGovernanceError` (`Component #2 base exception`)
to guarantee clean handling and HTTP status translation by Stage 7 (`FastAPI Router`).
"""

from app.audit.exceptions import FlourishGovernanceError


class IngestionError(FlourishGovernanceError):
    """Base exception class for all Component #3 ingestion and service failures."""
    pass


class NamespaceNotFoundError(IngestionError):
    """
    Raised when the target `domain_namespace` does not physically exist
    inside the `namespaces` database table (`404 Not Found`).
    """
    pass


class NamespaceAccessDeniedError(IngestionError):
    """
    Raised when the calling identity (`CallerContext`) attempts to ingest into a valid
    `domain_namespace` that is outside their horizontal clearances (`allowed_namespaces`) (`403 Forbidden`).
    """
    pass


class SensitivityViolationError(IngestionError):
    """
    Raised when the requested `sensitivity_label` / level exceeds the calling identity's
    maximum vertical clearance (`caller.max_sensitivity_level`) (`403 Forbidden`).
    """
    pass


class EmbeddingDimensionError(IngestionError):
    """
    Raised when a provided `embedding` vector does not match the exact static schema dimension (`1536`)
    or contains non-finite floating-point values (`NaN` / `Infinity`) (`RSK-07`, `422 Unprocessable Entity`).
    """
    pass


class IngestionPayloadError(IngestionError):
    """
    Raised when input payload validation fails (`e.g., empty title/body or malformed sensitivity_label`) (`400 Bad Request`).
    """
    pass


__all__ = [
    "IngestionError",
    "NamespaceNotFoundError",
    "NamespaceAccessDeniedError",
    "SensitivityViolationError",
    "EmbeddingDimensionError",
    "IngestionPayloadError",
]
