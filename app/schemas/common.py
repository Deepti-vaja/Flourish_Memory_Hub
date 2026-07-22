"""
Common Pydantic DTO Schemas for Stage 7 API Controllers (`Section 26 / Option A`).
Enforces strict JSON boundaries and error serialization invariants.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseDTOSchema(BaseModel):
    """
    Base configuration for all Flourish Memory Hub DTO schemas.
    Enforces ORM attribute compatibility and extra key ignoring (`Pydantic 2.x safety`).
    """

    model_config = ConfigDict(
        from_attributes=True, extra="ignore", populate_by_name=True, arbitrary_types_allowed=True
    )


class ErrorResponse(BaseDTOSchema):
    """
    Standardized error payload returned across all HTTP status codes (`Section 14 & 26.7`).
    """

    error: str = Field(..., description="Unique error code taxonomy identifier")
    message: str = Field(..., description="Human-readable exception details")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional diagnostic dictionary"
    )


class StatusResponse(BaseDTOSchema):
    """
    Simple status acknowledgment DTO for operational endpoints.
    """

    status: str = Field(..., description="Execution status acknowledgment e.g., 'OK' or 'SUCCESS'")
    message: str | None = Field(default=None, description="Optional operational note")
