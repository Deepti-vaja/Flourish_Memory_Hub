"""
Stage 7 Audit Verification Controller (`GET /api/v1/audit/verify`).
Exposes Stage 2 Cryptographic HMAC-SHA256 ledger verification over ASGI/FastAPI.
Runs sequential $O(N)$ verification across all audit records.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db_transaction
from app.audit.chainer import AuditChainService
from app.schemas.audit import VerifyLedgerResponse

router = APIRouter()


@router.get(
    "/verify",
    response_model=VerifyLedgerResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic HMAC-SHA256 audit ledger integrity",
    description="Runs full sequential verification of all audit log rows against the server HMAC secret key (`Section 12 / RSK-04`)."
)
async def verify_ledger_endpoint(
    session: AsyncSession = Depends(get_db_transaction),
) -> VerifyLedgerResponse:
    audit_service = AuditChainService()
    verify_result = await audit_service.verify_integrity(session=session, secret_key=audit_service._secret_key)

    return VerifyLedgerResponse(
        compromised=verify_result.compromised,
        verified_records=verify_result.total_verified,
        last_verified_seal=None,
        message=verify_result.reason or "Verification complete.",
    )
