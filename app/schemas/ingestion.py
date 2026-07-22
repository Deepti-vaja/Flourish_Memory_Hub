"""
Ingestion Request and Response DTOs (`Stage 3 Engine / Section 13`).
Encapsulates payload validation before calling IngestionService.ingest_item.
"""

from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import BaseDTOSchema


class IngestItemRequest(BaseDTOSchema):
    """
    Client request payload for knowledge item ingestion.
    Enforces mandatory title, body, and horizontal/vertical clearance ceilings.
    """

    title: str = Field(..., min_length=1, max_length=512, description="Document title")
    body: str = Field(..., min_length=1, description="Raw knowledge content")
    namespace: str = Field(
        ..., min_length=1, max_length=255, description="Domain namespace (`eng.core`, `hr.secret`)"
    )
    sensitivity_level: int = Field(
        default=1, ge=1, le=4, description="Vertical clearance ceiling (`1 to 4`)"
    )
    source_uri: str | None = Field(default=None, max_length=1024, description="Lineage source URI")
    metadata: dict[str, Any] | None = Field(
        default=None, description="Optional custom metadata dict"
    )

    @field_validator("namespace")
    @classmethod
    def normalize_namespace(cls, v: str) -> str:
        return v.strip()


class IngestItemResponse(BaseDTOSchema):
    """
    Response DTO returned upon successful ingestion into zero-trust quarantine.
    Notice `status` is guaranteed to be 'PENDING' (`Section 13 Invariant`).
    """

    item_id: UUID = Field(..., description="Unique UUID v4 identifier of ingested item")
    status: str = Field(..., description="Initial lifecycle state (`guaranteed PENDING`)")
    version: int = Field(default=1, description="Item version increment")
