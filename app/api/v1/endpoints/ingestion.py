"""
Stage 7 Ingestion Controller (`POST /api/v1/ingestion/items`).
Exposes Stage 3 Zero-Trust Ingestion engine over ASGI/FastAPI.
Ensures that all ingested items land strictly inside `PENDING` quarantine (`Section 13 Invariant`).
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_caller_context, get_db_transaction
from app.audit.chainer import AuditChainService
from app.core.constants import SensitivityLabelEnum
from app.security.context import CallerContext
from app.services.ingestion import IngestionService, SENSITIVITY_LEVEL_MAP
from app.schemas.ingestion import IngestItemRequest, IngestItemResponse

router = APIRouter()


@router.post(
    "/items",
    response_model=IngestItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest knowledge item into zero-trust quarantine",
    description="Validates and ingests document content. Item status is locked to 'PENDING' until Data Steward 4-Eyes adjudication."
)
async def ingest_item_endpoint(
    payload: IngestItemRequest,
    session: AsyncSession = Depends(get_db_transaction),
    caller: CallerContext = Depends(get_caller_context),
) -> IngestItemResponse:
    audit_service = AuditChainService()
    ingestion_service = IngestionService(audit_service=audit_service)

    # Convert numeric sensitivity level to enum claim
    level_to_enum = {v: k for k, v in SENSITIVITY_LEVEL_MAP.items()}
    sensitivity_enum = level_to_enum.get(payload.sensitivity_level, SensitivityLabelEnum.PUBLIC)

    raw_result = await ingestion_service.ingest_item(
        session=session,
        caller=caller,
        title=payload.title,
        body=payload.body,
        source_uri=payload.source_uri,
        domain_namespace=payload.namespace,
        sensitivity_label=sensitivity_enum,
        details=payload.metadata,
    )

    return IngestItemResponse.model_validate(raw_result)
