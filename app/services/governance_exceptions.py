"""
Flourish Governed Memory Hub - Governance Exception Hierarchy (`Component #4`)
Defines the clean domain exception classes for Stage 4 Governance Adjudication (`Section 14`).
All exceptions strictly inherit from `FlourishGovernanceError` (`Component #2 base exception`)
to guarantee clean handling and HTTP status translation by Stage 7 (`FastAPI Router`).
Created as an independent module (`Option A Zero Modifications`) to preserve Component #3 immutability.
"""

from app.audit.exceptions import FlourishGovernanceError


class GovernanceError(FlourishGovernanceError):
    """Base exception class for all Component #4 governance adjudication failures (`500 / General Domain Error`)."""

    pass


class DocumentNotFoundError(GovernanceError):
    """
    Raised when the target `item_id` does not physically exist inside the `knowledge_items` table (`404 Not Found`).
    """

    pass


class StewardAuthorizationError(GovernanceError):
    """
    Raised when the calling identity (`CallerContext`) lacks `STEWARD` or `ADMIN` functional role,
    or attempts to adjudicate an item outside their horizontal (`allowed_namespaces`) or vertical (`max_sensitivity_level`)
    clearances (`403 Forbidden`).
    """

    pass


class FourEyesPrincipleViolationError(GovernanceError):
    """
    Raised when the adjudicating steward (`caller.user_id`) is identical to the document's uploader (`ingested_by_id`),
    violating the Four-Eyes Principle (`Brief P10 BR-05`, `Section 12`, `403 Forbidden`).
    Traps both Python-level pre-checks and database-level `SQLSTATE 23514` check violations (`trg_governance_four_eyes`).
    """

    pass


class DocumentNotPendingError(GovernanceError):
    """
    Raised when attempting to adjudicate a document whose current status is not `PENDING` (`409 Conflict`).
    """

    pass


class DocumentAlreadyApprovedError(DocumentNotPendingError):
    """
    Raised when attempting to adjudicate a document that has already been `APPROVED` (`409 Conflict`).
    Enforces idempotent adjudication safety (`Section 12`).
    """

    pass


class DocumentAlreadyRejectedError(DocumentNotPendingError):
    """
    Raised when attempting to adjudicate a document that has already been `REJECTED` (`409 Conflict`).
    Enforces idempotent adjudication safety (`Section 12`).
    """

    pass


__all__ = [
    "GovernanceError",
    "DocumentNotFoundError",
    "StewardAuthorizationError",
    "FourEyesPrincipleViolationError",
    "DocumentNotPendingError",
    "DocumentAlreadyApprovedError",
    "DocumentAlreadyRejectedError",
]
