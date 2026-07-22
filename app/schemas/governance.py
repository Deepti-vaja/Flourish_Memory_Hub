"""
Governance Request and Response DTOs (`Stage 4 Engine / Section 14`).
Encapsulates Four-Eyes adjudication payloads (`approve vs reject`).
"""

from uuid import UUID

from pydantic import AliasChoices, Field, field_validator

from app.schemas.common import BaseDTOSchema


class AdjudicateItemRequest(BaseDTOSchema):
    """
    Steward adjudication request payload.
    Requires explicit action (`approve` vs `reject`) and mandatory justification string (`RSK-02`).
    """

    action: str = Field(..., description="Decision string (`approve` or `reject`)")
    justification: str = Field(
        ..., min_length=1, max_length=1024, description="Mandatory audit justification"
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        clean_action = v.strip().lower()
        if clean_action not in {"approve", "reject"}:
            raise ValueError("Action must be exactly 'approve' or 'reject'")
        return clean_action


class AdjudicateItemResponse(BaseDTOSchema):
    """
    Response DTO acknowledging pointer shift (`ACTIVE vs REJECTED`).
    """

    item_id: UUID = Field(..., description="UUID v4 of adjudicated knowledge item")
    status: str = Field(
        ...,
        validation_alias=AliasChoices("status", "decision"),
        description="New pointer state (`ACTIVE` or `REJECTED`)",
    )
    justification: str = Field(..., description="Steward justification recorded in audit ledger")


class PendingItemResponse(BaseDTOSchema):
    """
    Response DTO for an item in the governance pending queue.
    """

    item_id: UUID = Field(..., description="UUID v4 of pending item")
    title: str = Field(..., description="Document title")
    body: str = Field(..., description="Document text content")
    namespace: str = Field(
        ...,
        validation_alias=AliasChoices("namespace", "domain_namespace"),
        description="Domain namespace",
    )
    sensitivity_level: int = Field(..., description="Vertical sensitivity ceiling")
    status: str = Field(..., description="Current lifecycle state (`guaranteed PENDING`)")
    version: int = Field(default=1, description="Item version increment")
    created_at: str | None = Field(default=None, description="Ingestion timestamp")
