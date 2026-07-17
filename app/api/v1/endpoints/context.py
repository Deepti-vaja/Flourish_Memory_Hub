"""
Stage 7 Context Assembly Controller (`POST /api/v1/context/assemble`).
Exposes Stage 6 Context Assembly and 3-Stage Prompt Injection Defense Engine over ASGI/FastAPI.
Generates structural XML/CDTA citations with atomic token budgeting.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_caller_context, get_db_transaction
from app.audit.chainer import AuditChainService
from app.security.context import CallerContext
from app.services.context_assembly import ContextAssemblyService
from app.services.retrieval import RetrievalService
from app.schemas.context import AssembleContextRequest, AssembleContextResponse

router = APIRouter()


@router.post(
    "/assemble",
    response_model=AssembleContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Assemble sanitized, lineage-tracked context block",
    description="Retrieves active items matching query or explicit IDs, applies 3-Stage NFKC/XML sanitization and prompt injection trapping, and packs atomically within max token ceilings."
)
async def assemble_context_endpoint(
    payload: AssembleContextRequest,
    session: AsyncSession = Depends(get_db_transaction),
    caller: CallerContext = Depends(get_caller_context),
) -> AssembleContextResponse:
    audit_service = AuditChainService()
    retrieval_service = RetrievalService(audit_service=audit_service)
    context_service = ContextAssemblyService(retrieval_service=retrieval_service, audit_service=audit_service)

    raw_result = await context_service.assemble_context(
        session=session,
        caller=caller,
        query_text=payload.query,
        explicit_item_ids=payload.explicit_item_ids,
        max_tokens=payload.max_tokens,
    )

    if isinstance(raw_result, dict):
        if "manifest" not in raw_result and "lineage_manifest" in raw_result:
            raw_result["manifest"] = raw_result["lineage_manifest"]
        if "tokens_consumed" not in raw_result and "tokens_used" in raw_result:
            raw_result["tokens_consumed"] = raw_result["tokens_used"]
        if "items_packed" not in raw_result and "items_included" in raw_result:
            raw_result["items_packed"] = raw_result["items_included"]
        if "items_omitted" not in raw_result:
            raw_result["items_omitted"] = (
                raw_result.get("items_omitted_budget", 0)
                + raw_result.get("items_omitted_clearance", 0)
                + raw_result.get("items_rejected_injection", 0)
            )
        for m_entry in raw_result.get("manifest", []):
            if isinstance(m_entry, dict) and "namespace" not in m_entry and "domain_namespace" in m_entry:
                m_entry["namespace"] = m_entry["domain_namespace"]

    return AssembleContextResponse.model_validate(raw_result)
