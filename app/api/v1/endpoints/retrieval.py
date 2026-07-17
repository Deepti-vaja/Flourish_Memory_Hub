"""
Stage 7 Retrieval Controller (`POST /api/v1/retrieval/search` and `GET /api/v1/retrieval/items/{item_id}`).
Exposes Stage 5 hybrid retrieval engine over ASGI/FastAPI under strict clearance and active-only gating.
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_caller_context, get_db_transaction
from app.audit.chainer import AuditChainService
from app.security.context import CallerContext
from app.services.retrieval import RetrievalService
from app.schemas.retrieval import SearchRequest, SearchHitResponse, GetItemResponse

router = APIRouter()


@router.post(
    "/search",
    response_model=List[SearchHitResponse],
    status_code=status.HTTP_200_OK,
    summary="Execute clearance-scoped hybrid retrieval",
    description="Searches active knowledge items strictly within the caller's allowed namespaces and vertical sensitivity ceiling."
)
async def search_items_endpoint(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_db_transaction),
    caller: CallerContext = Depends(get_caller_context),
) -> List[SearchHitResponse]:
    audit_service = AuditChainService()
    retrieval_service = RetrievalService(audit_service=audit_service)

    raw_hits = await retrieval_service.search(
        session=session,
        caller=caller,
        query_text=payload.query,
        limit=payload.top_k,
    )

    clean_hits = []
    for hit in raw_hits:
        if isinstance(hit, dict):
            if "namespace" not in hit and "domain_namespace" in hit:
                hit["namespace"] = hit["domain_namespace"]
        clean_hits.append(SearchHitResponse.model_validate(hit))

    return clean_hits


@router.get(
    "/items/{item_id}",
    response_model=GetItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch single active knowledge item by UUID",
    description="Retrieves item details if active and within caller's clearance boundaries."
)
async def get_item_endpoint(
    item_id: UUID,
    session: AsyncSession = Depends(get_db_transaction),
    caller: CallerContext = Depends(get_caller_context),
) -> GetItemResponse:
    audit_service = AuditChainService()
    retrieval_service = RetrievalService(audit_service=audit_service)

    raw_item = await retrieval_service.get_item_by_id(
        session=session,
        caller=caller,
        item_id=item_id,
    )

    if isinstance(raw_item, dict):
        if "namespace" not in raw_item and "domain_namespace" in raw_item:
            raw_item["namespace"] = raw_item["domain_namespace"]

    return GetItemResponse.model_validate(raw_item)
