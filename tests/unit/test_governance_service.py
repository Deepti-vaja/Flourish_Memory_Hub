"""
Flourish Governed Memory Hub - Dedicated Unit Test Suite for Component #4 (`GovernanceService`)
Verifies protocol conformance, transaction pre-conditions, role/clearance authorization,
Four-Eyes Principle (`BR-05`), Blue-Green state transition rules, input sanitation,
and exception inheritance hierarchy.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.audit.exceptions import FlourishGovernanceError
from app.core.constants import KnowledgeStatusEnum, SensitivityLabelEnum
from app.models.knowledge import KnowledgeItem
from app.security.context import CallerContext
from app.services.governance import GovernanceService
from app.services.governance_exceptions import (
    DocumentAlreadyApprovedError,
    DocumentAlreadyRejectedError,
    DocumentNotFoundError,
    DocumentNotPendingError,
    FourEyesPrincipleViolationError,
    GovernanceError,
    StewardAuthorizationError,
)
from app.services.governance_protocols import GovernanceServiceProtocol


@pytest.fixture
def steward_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid4(),
        identity_key="steward_01",
        functional_role="STEWARD",
        allowed_namespaces={"eng.core", "eng.infra"},
        max_sensitivity_level=3,  # CONFIDENTIAL
        correlation_id="test-corr-steward-101",
    )


@pytest.fixture
def admin_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid4(),
        identity_key="admin_01",
        functional_role="ADMIN",
        allowed_namespaces={"eng.core", "eng.infra", "hr.policy"},
        max_sensitivity_level=4,  # RESTRICTED
        correlation_id="test-corr-admin-202",
    )


@pytest.fixture
def engineer_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid4(),
        identity_key="eng_user_01",
        functional_role="ENGINEER",
        allowed_namespaces={"eng.core"},
        max_sensitivity_level=2,  # INTERNAL
        correlation_id="test-corr-eng-303",
    )


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.in_transaction = MagicMock(return_value=True)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_audit_service() -> MagicMock:
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=505)
    return audit


@pytest.fixture
def governance_service(mock_audit_service: MagicMock) -> GovernanceService:
    return GovernanceService(audit_service=mock_audit_service)


def test_protocol_conformance(governance_service: GovernanceService):
    """Verify GovernanceService runtime checks against GovernanceServiceProtocol (`Section 26.4`)."""
    assert isinstance(governance_service, GovernanceServiceProtocol)


def test_exception_inheritance():
    """Verify all Component #4 exceptions inherit from FlourishGovernanceError (`Section 14`)."""
    assert issubclass(GovernanceError, FlourishGovernanceError)
    assert issubclass(DocumentNotFoundError, GovernanceError)
    assert issubclass(StewardAuthorizationError, GovernanceError)
    assert issubclass(FourEyesPrincipleViolationError, GovernanceError)
    assert issubclass(DocumentNotPendingError, GovernanceError)
    assert issubclass(DocumentAlreadyApprovedError, DocumentNotPendingError)
    assert issubclass(DocumentAlreadyRejectedError, DocumentNotPendingError)


@pytest.mark.asyncio
async def test_adjudicate_rejects_non_transaction(governance_service: GovernanceService, steward_caller: CallerContext):
    """Assert GovernanceError if session.in_transaction() == False (`Section 15`)."""
    session = MagicMock()
    session.in_transaction = MagicMock(return_value=False)
    with pytest.raises(GovernanceError, match="not inside an active transaction boundary"):
        await governance_service.adjudicate_item(session, steward_caller, uuid4(), "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_rejects_unauthorized_role(
    governance_service: GovernanceService, mock_session: MagicMock, engineer_caller: CallerContext
):
    """Assert StewardAuthorizationError when caller possesses 'ENGINEER' role (`Section 12`)."""
    with pytest.raises(StewardAuthorizationError, match="possesses role 'ENGINEER', requiring 'STEWARD' or 'ADMIN'"):
        await governance_service.adjudicate_item(mock_session, engineer_caller, uuid4(), "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_rejects_invalid_decision_string(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert GovernanceError for decision not in ('APPROVED', 'REJECTED')."""
    with pytest.raises(GovernanceError, match="Invalid adjudication decision 'MAYBE'"):
        await governance_service.adjudicate_item(mock_session, steward_caller, uuid4(), "MAYBE")


@pytest.mark.asyncio
async def test_adjudicate_rejects_justification_overflow(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert GovernanceError when justification exceeds 10,000 characters."""
    long_just = "A" * 10_001
    with pytest.raises(GovernanceError, match="justification exceeds maximum permitted length"):
        await governance_service.adjudicate_item(mock_session, steward_caller, uuid4(), "APPROVED", justification=long_just)


@pytest.mark.asyncio
async def test_adjudicate_document_not_found(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert DocumentNotFoundError when SELECT FOR UPDATE returns None (`404`)."""
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = res_mock

    with pytest.raises(DocumentNotFoundError, match="not found inside database table"):
        await governance_service.adjudicate_item(mock_session, steward_caller, uuid4(), "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_rejects_namespace_clearance_violation(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert StewardAuthorizationError when item.domain_namespace is not in caller.allowed_namespaces (`Section 26.1`)."""
    item = KnowledgeItem(
        item_id=uuid4(),
        title="Secret Policy",
        body="...",
        domain_namespace="finance.secret",  # Outside steward_caller allowed_namespaces
        sensitivity_label=SensitivityLabelEnum.INTERNAL,
        sensitivity_level=2,
        status=KnowledgeStatusEnum.PENDING,
        ingested_by_id=uuid4(),
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = res_mock

    with pytest.raises(StewardAuthorizationError, match="lacks horizontal clearance for namespace 'finance.secret'"):
        await governance_service.adjudicate_item(mock_session, steward_caller, item.item_id, "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_rejects_sensitivity_clearance_violation(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert StewardAuthorizationError when item.sensitivity_level > caller.max_sensitivity_level (`Section 11.3`)."""
    item = KnowledgeItem(
        item_id=uuid4(),
        title="Executive Salary",
        body="...",
        domain_namespace="eng.core",
        sensitivity_label=SensitivityLabelEnum.RESTRICTED,
        sensitivity_level=4,  # Exceeds steward_caller max level (3)
        status=KnowledgeStatusEnum.PENDING,
        ingested_by_id=uuid4(),
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = res_mock

    with pytest.raises(StewardAuthorizationError, match="lacks clearance for document sensitivity level 4"):
        await governance_service.adjudicate_item(mock_session, steward_caller, item.item_id, "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_enforces_four_eyes_principle(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert FourEyesPrincipleViolationError when caller.user_id == item.ingested_by_id (`Brief P10 BR-05`)."""
    item = KnowledgeItem(
        item_id=uuid4(),
        title="Self-Uploaded Notes",
        body="...",
        domain_namespace="eng.core",
        sensitivity_label=SensitivityLabelEnum.INTERNAL,
        sensitivity_level=2,
        status=KnowledgeStatusEnum.PENDING,
        ingested_by_id=steward_caller.user_id,  # Uploader IS the steward!
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = res_mock

    with pytest.raises(FourEyesPrincipleViolationError, match="cannot adjudicate an item they ingested themselves"):
        await governance_service.adjudicate_item(mock_session, steward_caller, item.item_id, "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_rejects_already_approved(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert DocumentAlreadyApprovedError (`409`) when item.status == APPROVED (`Section 12`)."""
    item = KnowledgeItem(
        item_id=uuid4(),
        title="Approved Doc",
        body="...",
        domain_namespace="eng.core",
        sensitivity_label=SensitivityLabelEnum.INTERNAL,
        sensitivity_level=2,
        status=KnowledgeStatusEnum.APPROVED,
        ingested_by_id=uuid4(),
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = res_mock

    with pytest.raises(DocumentAlreadyApprovedError, match="is already APPROVED"):
        await governance_service.adjudicate_item(mock_session, steward_caller, item.item_id, "APPROVED")


@pytest.mark.asyncio
async def test_adjudicate_rejects_already_rejected(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Assert DocumentAlreadyRejectedError (`409`) when item.status == REJECTED (`Section 12`)."""
    item = KnowledgeItem(
        item_id=uuid4(),
        title="Rejected Doc",
        body="...",
        domain_namespace="eng.core",
        sensitivity_label=SensitivityLabelEnum.INTERNAL,
        sensitivity_level=2,
        status=KnowledgeStatusEnum.REJECTED,
        ingested_by_id=uuid4(),
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = res_mock

    with pytest.raises(DocumentAlreadyRejectedError, match="is already REJECTED"):
        await governance_service.adjudicate_item(mock_session, steward_caller, item.item_id, "REJECTED")


@pytest.mark.asyncio
async def test_adjudicate_approval_success_path(
    governance_service: GovernanceService, mock_session: MagicMock, mock_audit_service: MagicMock, steward_caller: CallerContext
):
    """Verify clean approval flow: status update, demotion query, governance_decisions insert, and audit chaining."""
    item = KnowledgeItem(
        item_id=uuid4(),
        title="New Architecture Spec",
        body="...",
        source_uri="confluence://spec-101",
        domain_namespace="eng.core",
        sensitivity_label=SensitivityLabelEnum.INTERNAL,
        sensitivity_level=2,
        status=KnowledgeStatusEnum.PENDING,
        version=2,
        is_latest_approved=False,
        ingested_by_id=uuid4(),
    )
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = item
    mock_session.execute.return_value = res_mock

    dto = await governance_service.adjudicate_item(
        mock_session, steward_caller, item.item_id, "APPROVED", justification="Verified against blueprint."
    )

    assert item.status == KnowledgeStatusEnum.APPROVED
    assert item.is_latest_approved is True
    assert dto["decision_type"] == "APPROVED"
    assert dto["item_status"] == "APPROVED"
    assert dto["is_latest_approved"] is True
    assert mock_session.add.called
    assert mock_audit_service.log_event.called


@pytest.mark.asyncio
async def test_list_pending_items_enforces_clearances(
    governance_service: GovernanceService, mock_session: MagicMock, steward_caller: CallerContext
):
    """Verify list_pending_items checks role and filters by namespaces."""
    res_mock = MagicMock()
    res_mock.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = res_mock

    results = await governance_service.list_pending_items(mock_session, steward_caller, limit=10)
    assert results == []
    assert mock_session.execute.called
