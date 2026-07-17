"""
Context Assembly Request and Response DTOs (`Stage 6 Engine / Section 26.6`).
Encapsulates multi-channel retrieval, 3-Stage sanitization, and atomic token packing.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field, AliasChoices
from app.schemas.common import BaseDTOSchema


class AssembleContextRequest(BaseDTOSchema):
    """
    Context assembly request payload.
    Supports search query and/or explicit item IDs, along with max token ceilings.
    """
    query: Optional[str] = Field(default=None, max_length=2048, description="Optional search query string")
    explicit_item_ids: Optional[List[UUID]] = Field(default=None, description="Optional explicit list of UUID v4 IDs to include")
    max_tokens: int = Field(default=2048, ge=256, le=32768, description="Maximum token ceiling for assembled context block")


class ContextManifestEntry(BaseDTOSchema):
    """
    Individual lineage entry inside the packed context manifest (`Stage 6 Output`).
    """
    item_id: UUID = Field(..., description="UUID v4 of packed knowledge item")
    namespace: str = Field(..., validation_alias=AliasChoices("namespace", "domain_namespace"), description="Domain namespace")
    score: float = Field(..., description="Retrieval score (`or 1.0 if explicit`)")
    version: int = Field(..., description="Exact version increment packed")
    content_hash: str = Field(..., description="Cryptographic SHA-256 hash seal of packed text")


class AssembleContextResponse(BaseDTOSchema):
    """
    Response DTO containing the structural XML/CDTA prompt payload and 2-hop audit manifest.
    """
    assembled_prompt: str = Field(..., description="Sanitized, structural <knowledge_citation> XML payload")
    manifest: List[ContextManifestEntry] = Field(..., validation_alias=AliasChoices("manifest", "lineage_manifest"), description="2-hop cryptographic lineage manifest")
    tokens_consumed: int = Field(..., validation_alias=AliasChoices("tokens_consumed", "tokens_used"), description="Total token budget consumed by system frame + items")
    items_packed: int = Field(..., validation_alias=AliasChoices("items_packed", "items_included"), description="Number of items packed into prompt")
    items_omitted: int = Field(..., validation_alias=AliasChoices("items_omitted", "items_omitted_budget"), description="Number of items omitted due to atomic token ceiling")
