"""
Stage 7 Governance Controller (`POST /api/v1/governance/adjudicate/{item_id}`).
Exposes Stage 4 Four-Eyes Governance adjudication over ASGI/FastAPI.
Enforces separation of duties (`caller.user_id != item.ingested_by_id`) and mandatory justification (`RSK-02`).
"""
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_caller_context, get_db_transaction
from app.audit.chainer import AuditChainService
from app.security.context import CallerContext
from app.services.governance import GovernanceService
from app.schemas.governance import AdjudicateItemRequest, AdjudicateItemResponse

router = APIRouter()


@router.post(
    "/adjudicate/{item_id}",
    response_model=AdjudicateItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Four-Eyes Adjudication of quarantined item",
    description="Allows Data Stewards or Admins to approve or reject quarantined ('PENDING') knowledge items."
)
async def adjudicate_item_endpoint(
    item_id: UUID,
    payload: AdjudicateItemRequest,
    session: AsyncSession = Depends(get_db_transaction),
    caller: CallerContext = Depends(get_caller_context),
) -> AdjudicateItemResponse:
    audit_service = AuditChainService()
    governance_service = GovernanceService(audit_service=audit_service)

    # Convert action to APPROVED or REJECTED required by GovernanceService
    action_clean = payload.action.strip().lower()
    decision_str = "APPROVED" if action_clean == "approve" else "REJECTED"

    raw_result = await governance_service.adjudicate_item(
        session=session,
        caller=caller,
        item_id=item_id,
        decision=decision_str,
        justification=payload.justification,
    )

    if isinstance(raw_result, dict):
        if "status" not in raw_result:
            raw_result["status"] = raw_result.get("item_status") or raw_result.get("decision_type") or decision_str

    return AdjudicateItemResponse.model_validate(raw_result)
