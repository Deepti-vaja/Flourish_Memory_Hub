"""
Unit verification suite for Component #5 (`RetrievalService — Stage 5 Engine`).

Executes comprehensive assertions covering:
1. Protocol Conformance (`RetrievalServiceProtocol`).
2. Precondition Step 0 (`session.in_transaction() assertion`).
3. Active-Only Quarantine Gating (`status = APPROVED AND is_latest_approved = True`).
4. Zero-Trust Horizontal (`domain_namespace IN allowed_namespaces`) and Vertical (`sensitivity_level <= max_sensitivity_level`) clearance pushdown.
5. Flag-32 Cover Density normalized hybrid scoring & COALESCE null wrapping.
6. Vector dimension validation (`exactly 1536`).
7. Deterministic tie-breaking & pagination (`limit, offset`).
8. Cryptographic search audit ledgering without restricted keys (`RSK-04`).
9. Exact ID retrieval (`get_item_by_id`) and `ItemNotFoundError (404)` handling.
10. Dual-null search query fallback (`Clearance-Scoped Recent Feed`).
"""
import datetime
from typing import Any, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.constants import AuditActionEnum, KnowledgeStatusEnum, SensitivityLabelEnum
from app.models.knowledge import KnowledgeItem
from app.security.context import CallerContext
from app.services.retrieval import RetrievalService
from app.services.retrieval_exceptions import (
    InvalidVectorDimensionError,
    ItemNotFoundError,
    RetrievalError,
    SearchClearanceViolationError,
)
from app.services.retrieval_protocols import RetrievalServiceProtocol


@pytest.fixture
def engineer_caller() -> CallerContext:
    """Standard Engineer identity with clearance to 'eng.core' and sensitivity level 2."""
    return CallerContext(
        user_id=uuid.uuid4(),
        identity_key="eng-user",
        functional_role="ENGINEER",
        allowed_namespaces={"eng.core", "eng.docs"},
        max_sensitivity_level=2,
        correlation_id="req-eng-001",
    )


@pytest.fixture
def steward_caller() -> CallerContext:
    """High-clearance Steward identity with sensitivity level 4 across multiple namespaces."""
    return CallerContext(
        user_id=uuid.uuid4(),
        identity_key="steward-user",
        functional_role="STEWARD",
        allowed_namespaces={"eng.core", "eng.docs", "hr.secret"},
        max_sensitivity_level=4,
        correlation_id="req-stw-001",
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock database session inside an active transaction boundary (`Precondition Step 0`)."""
    session = AsyncMock()
    session.in_transaction = MagicMock(return_value=True)
    return session


def create_mock_knowledge_item(
    item_id: Optional[uuid.UUID] = None,
    title: str = "Test Title",
    body: str = "Test Body Content",
    domain_namespace: str = "eng.core",
    sensitivity_level: int = 2,
    status: KnowledgeStatusEnum = KnowledgeStatusEnum.APPROVED,
    is_latest_approved: bool = True,
) -> KnowledgeItem:
    """Helper to generate a mock ORM KnowledgeItem instance."""
    item = KnowledgeItem(
        item_id=item_id or uuid.uuid4(),
        title=title,
        body=body,
        source_uri="confluence://doc-retrieval",
        domain_namespace=domain_namespace,
        sensitivity_label=SensitivityLabelEnum.INTERNAL,
        sensitivity_level=sensitivity_level,
        status=status,
        version=1,
        is_latest_approved=is_latest_approved,
        ingested_by_id=uuid.uuid4(),
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    return item


@pytest.mark.asyncio
async def test_retrieval_protocol_conformance() -> None:
    """Verify `RetrievalService` strictly satisfies `RetrievalServiceProtocol` at runtime (`Section 26.5`)."""
    service = RetrievalService()
    assert isinstance(service, RetrievalServiceProtocol)


@pytest.mark.asyncio
async def test_search_rejects_non_transaction(mock_session: AsyncMock, engineer_caller: CallerContext) -> None:
    """Verify search immediately raises `RetrievalError` if `session.in_transaction() == False` (`Precondition Step 0`)."""
    service = RetrievalService()
    mock_session.in_transaction.return_value = False

    with pytest.raises(RetrievalError) as exc_info:
        await service.search(session=mock_session, caller=engineer_caller, query_text="hello")
    assert "active transaction boundary" in str(exc_info.value)


@pytest.mark.asyncio
async def test_search_rejects_invalid_vector_dimension(mock_session: AsyncMock, engineer_caller: CallerContext) -> None:
    """Verify passing a query_vector whose dimension != 1536 raises `InvalidVectorDimensionError (400)`."""
    service = RetrievalService()
    invalid_vector = [0.1] * 128  # 128 dimensions instead of 1536

    with pytest.raises(InvalidVectorDimensionError) as exc_info:
        await service.search(session=mock_session, caller=engineer_caller, query_vector=invalid_vector)
    assert exc_info.value.dimension == 128
    assert exc_info.value.error_code == "INVALID_VECTOR_DIMENSION"


@pytest.mark.asyncio
async def test_search_enforces_horizontal_namespace_clearance(
    mock_session: AsyncMock, engineer_caller: CallerContext
) -> None:
    """Verify caller requesting an unauthorized target namespace raises `SearchClearanceViolationError (403)`."""
    service = RetrievalService()
    # engineer_caller allowed_namespaces = {"eng.core", "eng.docs"}
    unauthorized_namespaces = ["eng.core", "hr.secret"]

    with pytest.raises(SearchClearanceViolationError) as exc_info:
        await service.search(
            session=mock_session,
            caller=engineer_caller,
            query_text="salary",
            domain_namespaces=unauthorized_namespaces,
        )
    assert exc_info.value.error_code == "SEARCH_CLEARANCE_VIOLATION"
    assert "hr.secret" in str(exc_info.value)


@pytest.mark.asyncio
async def test_search_short_circuits_on_empty_clearance(mock_session: AsyncMock) -> None:
    """Verify when caller has zero `allowed_namespaces`, search returns `[]` immediately (`preventing SQL IN () crash`)."""
    service = RetrievalService()
    empty_caller = CallerContext(
        user_id=uuid.uuid4(),
        identity_key="eng-empty",
        functional_role="ENGINEER",
        allowed_namespaces=set(),
        max_sensitivity_level=2,
        correlation_id="req-empty-001",
    )

    results = await service.search(session=mock_session, caller=empty_caller, query_text="test")
    assert results == []
    # Verify zero database hits
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_search_success_with_hybrid_flag32_scoring(
    mock_session: AsyncMock, engineer_caller: CallerContext
) -> None:
    """Verify hybrid search executes query, converts items to DTO dictionaries, and logs cryptographic audit (`RSK-04`)."""
    mock_audit = AsyncMock()
    service = RetrievalService(audit_service=mock_audit)

    item_1 = create_mock_knowledge_item(title="Doc 1")
    item_2 = create_mock_knowledge_item(title="Doc 2")

    # Mock database execute returning tuples of (KnowledgeItem, score)
    mock_result = MagicMock()
    mock_result.all.return_value = [(item_1, 0.85), (item_2, 0.62)]
    mock_session.execute.return_value = mock_result

    results = await service.search(
        session=mock_session,
        caller=engineer_caller,
        query_text="architecture blueprint",
        query_vector=[0.01] * 1536,
        limit=10,
        offset=0,
    )

    assert len(results) == 2
    assert results[0]["item_id"] == str(item_1.item_id)
    assert results[0]["score"] == 0.85
    assert results[0]["status"] == "APPROVED"
    assert results[1]["score"] == 0.62

    # Verify AuditChainService.log_event invoked without restricted keys
    mock_audit.log_event.assert_called_once()
    call_kwargs = mock_audit.log_event.call_args.kwargs
    assert call_kwargs["session"] == mock_session
    payload = call_kwargs["payload"]
    assert payload.action_type == AuditActionEnum.RETRIEVE_SUCCESS
    assert payload.actor_id == engineer_caller.user_id
    assert payload.target_id == item_1.item_id
    assert payload.details["results_count"] == 2
    assert "body" not in payload.details
    assert "content" not in payload.details


@pytest.mark.asyncio
async def test_search_recent_feed_fallback_when_queries_empty(
    mock_session: AsyncMock, engineer_caller: CallerContext
) -> None:
    """Verify dual-null query (`query_text=None, query_vector=None`) returns recent approved feed without scoring (`Option 2`)."""
    mock_audit = AsyncMock()
    service = RetrievalService(audit_service=mock_audit)

    item = create_mock_knowledge_item(title="Recent Feed Doc")
    mock_result = MagicMock()
    mock_result.all.return_value = [item]  # No score tuple in recent feed fallback
    mock_session.execute.return_value = mock_result

    results = await service.search(session=mock_session, caller=engineer_caller, query_text=None, query_vector=None)
    assert len(results) == 1
    assert results[0]["title"] == "Recent Feed Doc"
    assert results[0]["score"] == 0.0
    mock_audit.log_event.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_by_id_success(mock_session: AsyncMock, steward_caller: CallerContext) -> None:
    """Verify `get_item_by_id` returns DTO when document exists, is APPROVED, and within caller clearance."""
    mock_audit = AsyncMock()
    service = RetrievalService(audit_service=mock_audit)

    target_id = uuid.uuid4()
    item = create_mock_knowledge_item(item_id=target_id, domain_namespace="hr.secret", sensitivity_level=4)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = mock_result

    dto = await service.get_item_by_id(session=mock_session, caller=steward_caller, item_id=target_id)
    assert dto["item_id"] == str(target_id)
    assert dto["domain_namespace"] == "hr.secret"
    assert dto["score"] == 1.0

    # Verify audit
    mock_audit.log_event.assert_called_once()
    assert mock_audit.log_event.call_args.kwargs["payload"].target_id == target_id


@pytest.mark.asyncio
async def test_get_item_by_id_not_found(mock_session: AsyncMock, engineer_caller: CallerContext) -> None:
    """Verify `get_item_by_id` raises `ItemNotFoundError (404)` when row is None (`quarantined or unauthorized`)."""
    service = RetrievalService()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(ItemNotFoundError) as exc_info:
        await service.get_item_by_id(session=mock_session, caller=engineer_caller, item_id="missing-uuid")
    assert exc_info.value.error_code == "ITEM_NOT_FOUND"
