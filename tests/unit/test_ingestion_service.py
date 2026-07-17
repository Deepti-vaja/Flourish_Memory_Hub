"""
Flourish Governed Memory Hub - Dedicated Unit Test Suite for Component #3 (`IngestionService`)
Verifies protocol conformance, exception inheritance hierarchy, DTO validation, null-byte cleaning,
vector dimension/NaN validation (`RSK-07`), sensitivity mapping, and clearance validation.
"""

import math
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.audit.chainer import AuditActionEnum
from app.audit.exceptions import FlourishGovernanceError
from app.core.constants import KnowledgeStatusEnum, SensitivityLabelEnum
from app.security.context import CallerContext
from app.services import (
    EmbeddingDimensionError,
    IngestionError,
    IngestionPayloadError,
    IngestionService,
    IngestionServiceProtocol,
    NamespaceAccessDeniedError,
    NamespaceNotFoundError,
    SensitivityViolationError,
)
from app.services.ingestion import _clean_text


@pytest.fixture
def dummy_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid4(),
        identity_key="eng_user_01",
        functional_role="ENGINEER",
        allowed_namespaces={"eng.core", "eng.infra"},
        max_sensitivity_level=3,  # CONFIDENTIAL
        correlation_id="test-corr-123",
    )


@pytest.fixture
def mock_audit_service() -> MagicMock:
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=101)
    return audit


def test_protocol_conformance(mock_audit_service: MagicMock) -> None:
    service = IngestionService(mock_audit_service)
    assert isinstance(service, IngestionServiceProtocol)


def test_exception_inheritance_hierarchy() -> None:
    assert issubclass(IngestionError, FlourishGovernanceError)
    assert issubclass(NamespaceNotFoundError, IngestionError)
    assert issubclass(NamespaceAccessDeniedError, IngestionError)
    assert issubclass(SensitivityViolationError, IngestionError)
    assert issubclass(EmbeddingDimensionError, IngestionError)
    assert issubclass(IngestionPayloadError, IngestionError)


def test_clean_text_strips_null_bytes() -> None:
    raw = "Hello \x00World! \x00"
    assert _clean_text(raw) == "Hello World!"
    assert _clean_text("   ") is None
    assert _clean_text(None) is None


@pytest.mark.asyncio
async def test_ingest_rejects_closed_or_non_transaction_session(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=False)

    with pytest.raises(IngestionError, match="not inside an active transaction boundary"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_empty_title_or_body(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    with pytest.raises(IngestionPayloadError, match="must be non-empty strings"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="",
            body="Valid Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_oversized_body(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    oversized_body = "A" * 10_000_005
    with pytest.raises(IngestionPayloadError, match="exceeds maximum permitted size"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Valid Title",
            body=oversized_body,
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_invalid_sensitivity_label(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    with pytest.raises(IngestionPayloadError, match="Invalid sensitivity label"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Valid Title",
            body="Valid Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label="TOP_SECRET",
        )


@pytest.mark.asyncio
async def test_ingest_enforces_namespace_existence(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    # Mock namespace select returning None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    fake_session.execute.return_value = mock_result

    with pytest.raises(NamespaceNotFoundError, match="does not exist"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="nonexistent.ns",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_enforces_horizontal_namespace_clearance(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    # Mock namespace select returning a valid row
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    fake_session.execute.return_value = mock_result

    with pytest.raises(NamespaceAccessDeniedError, match="is not authorized for namespace"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="hr.layoffs",  # Outside dummy_caller allowed_namespaces
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_enforces_vertical_sensitivity_clearance(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    fake_session.execute.return_value = mock_result

    # dummy_caller max_sensitivity_level is 3 (CONFIDENTIAL)
    with pytest.raises(SensitivityViolationError, match="exceeds caller maximum clearance"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.RESTRICTED,  # Level 4
        )


@pytest.mark.asyncio
async def test_ingest_rejects_malformed_embedding_dimensions(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    fake_session.execute.return_value = mock_result

    # Pass 1024 dimensions instead of 1536
    bad_vector = [0.1] * 1024
    with pytest.raises(EmbeddingDimensionError, match="must contain exactly 1536 dimensions"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
            embedding=bad_vector,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_nan_and_infinity_in_embedding(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    fake_session.execute.return_value = mock_result

    # Pass NaN
    nan_vector = [float("nan")] + [0.1] * 1535
    with pytest.raises(EmbeddingDimensionError, match="contains non-finite floating-point values"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
            embedding=nan_vector,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_malformed_caller_context_clearances(
    mock_audit_service: MagicMock
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    # Malformed caller with allowed_namespaces=None (`DEF-03`)
    bad_caller = CallerContext(
        user_id=uuid4(),
        identity_key="eng_user_bad",
        functional_role="ENGINEER",
        allowed_namespaces=None,  # type: ignore[arg-type]
        max_sensitivity_level=3,
        correlation_id="bad-corr",
    )
    with pytest.raises(IngestionError, match="Invalid or missing CallerContext identity or clearance attributes"):
        await service.ingest_item(
            session=fake_session,
            caller=bad_caller,
            title="Title",
            body="Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_oversized_title_or_uri(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    # 1. Check title > 255 (`DEF-01`)
    with pytest.raises(IngestionPayloadError, match="Document title exceeds maximum length of 255 characters"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="T" * 256,
            body="Valid Body",
            source_uri=None,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )

    # 2. Check uri > 512 (`DEF-01`)
    with pytest.raises(IngestionPayloadError, match="Document source_uri exceeds maximum length of 512 characters"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Valid Title",
            body="Valid Body",
            source_uri="confluence://" + "U" * 510,
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )


@pytest.mark.asyncio
async def test_ingest_rejects_cross_namespace_uri_collision_path_a(
    mock_audit_service: MagicMock, dummy_caller: CallerContext
) -> None:
    service = IngestionService(mock_audit_service)
    fake_session = AsyncMock()
    fake_session.in_transaction = MagicMock(return_value=True)

    # Mock namespace existence returning valid row
    mock_ns_result = MagicMock()
    mock_ns_result.scalar_one_or_none.return_value = MagicMock()

    # Mock existing_ns_result returning 'hr.policy' when ingesting into 'eng.core' (`DEF-02 Path A`)
    mock_existing_ns_result = MagicMock()
    mock_existing_ns_result.scalar_one_or_none.return_value = "hr.policy"

    fake_session.execute.side_effect = [
        mock_ns_result,           # Step 5: check domain_namespace exists
        MagicMock(),              # Step 7: pg_advisory_xact_lock
        mock_existing_ns_result,  # Step 7: existing_ns check (`DEF-02 Path A`)
    ]

    with pytest.raises(IngestionPayloadError, match="is already registered under namespace 'hr.policy'; cannot ingest across different namespaces"):
        await service.ingest_item(
            session=fake_session,
            caller=dummy_caller,
            title="Valid Title",
            body="Valid Body",
            source_uri="confluence://company/shared-doc",
            domain_namespace="eng.core",
            sensitivity_label=SensitivityLabelEnum.INTERNAL,
        )
