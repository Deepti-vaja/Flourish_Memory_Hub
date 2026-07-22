"""
Retrieval Request and Response DTOs (`Stage 5 Engine / Section 13`).
Encapsulates clearance-scoped hybrid search (`pgvector HNSW + tsvector GIN`).
"""

from typing import Any
from uuid import UUID

from pydantic import AliasChoices, Field

from app.schemas.common import BaseDTOSchema


class SearchRequest(BaseDTOSchema):
    """
    Search request payload for hybrid retrieval.
    """

    query: str = Field(
        ..., min_length=1, max_length=2048, description="Natural language search query"
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum candidate hits to return")
    alpha: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Hybrid RRF balance weighting (`0.5 default`)"
    )


class SearchHitResponse(BaseDTOSchema):
    """
    Individual search hit DTO returned inside search result listings.
    """

    item_id: UUID = Field(..., description="UUID v4 of retrieved item")
    score: float = Field(..., description="Hybrid Flag-32 cover density rank score")
    title: str = Field(..., description="Document title")
    body: str = Field(..., description="Document text content")
    namespace: str = Field(
        ...,
        validation_alias=AliasChoices("namespace", "domain_namespace"),
        description="Domain namespace",
    )
    sensitivity_level: int = Field(..., description="Vertical sensitivity ceiling")
    version: int = Field(default=1, description="Item version increment")


class GetItemResponse(BaseDTOSchema):
    """
    Detailed single item DTO returned when fetching by ID.
    """

    item_id: UUID = Field(..., description="UUID v4 of retrieved item")
    title: str = Field(..., description="Document title")
    body: str = Field(..., description="Document text content")
    namespace: str = Field(
        ...,
        validation_alias=AliasChoices("namespace", "domain_namespace"),
        description="Domain namespace",
    )
    sensitivity_level: int = Field(..., description="Vertical sensitivity ceiling")
    status: str = Field(..., description="Current lifecycle state (`guaranteed ACTIVE`)")
    version: int = Field(default=1, description="Item version increment")
    source_uri: str | None = Field(default=None, description="Lineage source URI")
    metadata: dict[str, Any] | None = Field(default=None, description="Item metadata dict")
