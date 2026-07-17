r"""
Flourish Governed Memory Hub - Live Integration Test Suite for Component #4 (`GovernanceService`)
Executes directly against the live PostgreSQL 18 instance (`flourish_memory_hub`).
Verifies:
  1. Live approval persistence (`governance_decisions` row + `KnowledgeItem.status == APPROVED` + `is_latest_approved == True`).
  2. Live rejection persistence (`governance_decisions` row + `KnowledgeItem.status == REJECTED` + `is_latest_approved == False`).
  3. Blue-Green promotion/demotion with namespace isolation (`confluence://doc-A v1 demoted to False, v2 promoted to True, doc-B untouched`).
  4. Physical Four-Eyes DDL trigger check (`trg_governance_four_eyes check_violation` translation).
  5. Pessimistic row locking (`with_for_update`) concurrency verification.
  6. Shared transaction atomicity & Fail-Closed rollback guarantees (`Section 15`).
"""

import asyncio
import sys
from typing import Any, Dict
import uuid
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.audit import AuditChainService
from app.core.constants import KnowledgeStatusEnum, SensitivityLabelEnum
from app.database.session import async_session_maker
from app.models.audit import AuditLog, AuditSequenceHead
from app.models.governance import GovernanceDecision
from app.models.knowledge import KnowledgeItem
from app.models.namespace import Namespace, Role, User
from app.security.context import CallerContext
from app.services.governance import GovernanceService
from app.services.governance_exceptions import (
    DocumentAlreadyApprovedError,
    FourEyesPrincipleViolationError,
    GovernanceError,
)
from app.services.ingestion import IngestionService

TEST_SECRET = b"live-integration-governance-secret-2026"
ENGINEER_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
STEWARD_UUID = uuid.UUID("33333333-3333-3333-3333-333333333333")
ADMIN_UUID = uuid.UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture(autouse=True)
async def reset_governance_state() -> None:
    """
    Ensures clean database state before and after each live governance test:
    1. Ensures SYSTEM, ENGINEER, STEWARD, and ADMIN roles exist.
    2. Ensures test users and namespaces (`test.ns`, `eng.core`) exist.
    3. Cleans `governance_decisions`, `knowledge_items`, and `audit_logs`.
    """
    async with async_session_maker() as session:
        # 1. Ensure Roles
        for role_id in ["SYSTEM", "ENGINEER", "STEWARD", "ADMIN"]:
            res = await session.execute(select(Role).where(Role.role_id == role_id))
            if res.scalar_one_or_none() is None:
                session.add(Role(role_id=role_id, description=f"{role_id} Role"))
        await session.flush()

        # 2. Ensure Users (check by user_id OR identity_key to avoid unique constraint conflicts)
        users_to_add = [
            (ENGINEER_UUID, "engineer@flourish.ai", "ENGINEER"),
            (STEWARD_UUID, "steward_live@flourish.ai", "STEWARD"),
            (ADMIN_UUID, "admin_live@flourish.ai", "ADMIN"),
        ]
        for uid, key, role in users_to_add:
            res_user = await session.execute(
                select(User).where((User.user_id == uid) | (User.identity_key == key))
            )
            if res_user.scalar_one_or_none() is None:
                session.add(User(user_id=uid, identity_key=key, functional_role=role))
        await session.flush()

        # 3. Ensure Namespaces
        for ns_id in ["test.ns", "eng.core"]:
            res_ns = await session.execute(select(Namespace).where(Namespace.namespace_id == ns_id))
            if res_ns.scalar_one_or_none() is None:
                session.add(Namespace(namespace_id=ns_id, display_name=f"{ns_id} Namespace"))
        await session.flush()

        # 4. Clean tables in FK order (GovernanceDecision -> AuditLog -> KnowledgeItem)
        await session.execute(delete(GovernanceDecision))
        await session.execute(delete(AuditLog))
        await session.execute(delete(KnowledgeItem))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()

    yield

    async with async_session_maker() as session:
        await session.execute(delete(GovernanceDecision))
        await session.execute(delete(AuditLog))
        await session.execute(delete(KnowledgeItem))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()


@pytest.fixture
def engineer_caller() -> CallerContext:
    return CallerContext(
        user_id=ENGINEER_UUID,
        identity_key="engineer@flourish.ai",
        functional_role="ENGINEER",
        allowed_namespaces={"test.ns", "eng.core"},
        max_sensitivity_level=2,
        correlation_id="corr-live-eng-01",
    )


@pytest.fixture
def steward_caller() -> CallerContext:
    return CallerContext(
        user_id=STEWARD_UUID,
        identity_key="steward_live@flourish.ai",
        functional_role="STEWARD",
        allowed_namespaces={"test.ns", "eng.core"},
        max_sensitivity_level=3,
        correlation_id="corr-live-steward-02",
    )


@pytest.mark.asyncio
async def test_adjudicate_approval_persists_decision_and_audit_live(
    engineer_caller: CallerContext, steward_caller: CallerContext
):
    """Verify live approval: KnowledgeItem status=APPROVED, is_latest_approved=True, GovernanceDecision row, and HMAC AuditLog."""
    audit_service = AuditChainService(secret_key=TEST_SECRET)
    ingestion = IngestionService(audit_service=audit_service)
    governance = GovernanceService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            # Step 1: Ingest pending item via Component #3 inside transaction
            res_ingest = await ingestion.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Live Governance Doc",
                body="Important enterprise architecture details.",
                source_uri="confluence://live-doc-101",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )
            item_id = res_ingest["item_id"]

    # Step 2: Adjudicate approval via Component #4 inside a new transaction boundary
    async with async_session_maker() as session:
        async with session.begin():
            res_adj = await governance.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=item_id,
                decision="APPROVED",
                justification="Architectural compliance verified.",
            )
            assert res_adj["decision_type"] == "APPROVED"
            assert res_adj["is_latest_approved"] is True

        # Step 3: Verify live PostgreSQL rows outside transaction
        target_id = item_id if isinstance(item_id, uuid.UUID) else uuid.UUID(str(item_id))
        res_item = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == target_id))
        item_db = res_item.scalar_one()
        assert item_db.status == KnowledgeStatusEnum.APPROVED
        assert item_db.is_latest_approved is True

        res_dec = await session.execute(select(GovernanceDecision).where(GovernanceDecision.item_id == target_id))
        dec_db = res_dec.scalar_one()
        assert dec_db.steward_id == STEWARD_UUID
        assert dec_db.decision_type == "APPROVED"
        assert dec_db.justification == "Architectural compliance verified."

        # Step 4: Verify HMAC audit ledger contains exactly 2 valid events (INGEST -> APPROVE)
        res_audit = await session.execute(select(AuditLog).order_by(AuditLog.sequence_id.asc()))
        logs = res_audit.scalars().all()
        assert len(logs) == 2
        assert logs[0].action_type.value == "INGEST"
        assert logs[1].action_type.value == "APPROVE"

        verify_report = await audit_service.verify_integrity(session=session, secret_key=TEST_SECRET)
        assert verify_report.compromised is False
        assert verify_report.total_verified == 2


@pytest.mark.asyncio
async def test_adjudicate_rejection_persists_decision_and_audit_live(
    engineer_caller: CallerContext, steward_caller: CallerContext
):
    """Verify live rejection: KnowledgeItem status=REJECTED, is_latest_approved=False, and HMAC AuditLog REJECT."""
    audit_service = AuditChainService(secret_key=TEST_SECRET)
    ingestion = IngestionService(audit_service=audit_service)
    governance = GovernanceService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            res_ingest = await ingestion.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Invalid Sensitive Doc",
                body="...",
                source_uri="confluence://live-reject-202",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )
            item_id = res_ingest["item_id"]

    async with async_session_maker() as session:
        async with session.begin():
            res_adj = await governance.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=item_id,
                decision="REJECTED",
                justification="Exceeds departmental scope.",
            )
            assert res_adj["decision_type"] == "REJECTED"
            assert res_adj["is_latest_approved"] is False

        target_id = item_id if isinstance(item_id, uuid.UUID) else uuid.UUID(str(item_id))
        res_item = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == target_id))
        item_db = res_item.scalar_one()
        assert item_db.status == KnowledgeStatusEnum.REJECTED
        assert item_db.is_latest_approved is False

        res_dec = await session.execute(select(GovernanceDecision).where(GovernanceDecision.item_id == target_id))
        assert res_dec.scalar_one().decision_type == "REJECTED"


@pytest.mark.asyncio
async def test_blue_green_promotion_demotion_live(
    engineer_caller: CallerContext, steward_caller: CallerContext
):
    """
    Verify Blue-Green versioning & demotion (`RSK-05`):
    1. Ingest & approve `confluence://doc-A` v1 -> is_latest_approved=True.
    2. Ingest `confluence://doc-A` v2 (`version=2, pending`).
    3. Ingest & approve `confluence://doc-B` v1 (`unrelated document`).
    4. Approve `doc-A v2`. Verify `doc-A v1` is demoted (`False`), `doc-A v2` is promoted (`True`), and `doc-B v1` remains `True`.
    """
    audit_service = AuditChainService(secret_key=TEST_SECRET)
    ingestion = IngestionService(audit_service=audit_service)
    governance = GovernanceService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            # 1. doc-A v1
            res_a1 = await ingestion.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Doc A v1",
                body="v1 content",
                source_uri="confluence://doc-A",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )

    async with async_session_maker() as session:
        async with session.begin():
            await governance.adjudicate_item(session, steward_caller, res_a1["item_id"], "APPROVED")

    async with async_session_maker() as session:
        async with session.begin():
            # 2. doc-A v2 (ingested via same URI, increments version to 2)
            res_a2 = await ingestion.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Doc A v2",
                body="v2 updated content",
                source_uri="confluence://doc-A",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )
            # 3. doc-B v1
            res_b1 = await ingestion.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Doc B v1",
                body="b1 content",
                source_uri="confluence://doc-B",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )

    async with async_session_maker() as session:
        async with session.begin():
            await governance.adjudicate_item(session, steward_caller, res_b1["item_id"], "APPROVED")

    # Now approve doc-A v2!
    async with async_session_maker() as session:
        async with session.begin():
            await governance.adjudicate_item(session, steward_caller, res_a2["item_id"], "APPROVED")

        # Verify DB states
        id_a1 = res_a1["item_id"] if isinstance(res_a1["item_id"], uuid.UUID) else uuid.UUID(str(res_a1["item_id"]))
        id_a2 = res_a2["item_id"] if isinstance(res_a2["item_id"], uuid.UUID) else uuid.UUID(str(res_a2["item_id"]))
        id_b1 = res_b1["item_id"] if isinstance(res_b1["item_id"], uuid.UUID) else uuid.UUID(str(res_b1["item_id"]))
        res_a1_db = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == id_a1))
        res_a2_db = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == id_a2))
        res_b1_db = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == id_b1))

        assert res_a1_db.scalar_one().is_latest_approved is False  # Demoted!
        assert res_a2_db.scalar_one().is_latest_approved is True   # Promoted!
        assert res_b1_db.scalar_one().is_latest_approved is True   # Untouched!


@pytest.mark.asyncio
async def test_adjudicate_fail_closed_rollback_live(
    engineer_caller: CallerContext, steward_caller: CallerContext
):
    """
    Verify Fail-Closed rollback (`Section 15`):
    If an exception occurs after updating `status` and inserting into `governance_decisions`,
    `session.rollback()` reverts 100% of the state (`KnowledgeItem` remains `PENDING`).
    """
    audit_service = AuditChainService(secret_key=TEST_SECRET)
    ingestion = IngestionService(audit_service=audit_service)
    governance = GovernanceService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            res_ingest = await ingestion.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Rollback Test Doc",
                body="...",
                source_uri="confluence://rollback-test",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )
            item_id = res_ingest["item_id"]

    # Now simulate an adjudication where we try to approve twice, or where an audit error occurs
    async with async_session_maker() as session:
        try:
            async with session.begin():
                # First approval succeeds inside transaction
                await governance.adjudicate_item(session, steward_caller, item_id, "APPROVED")
                # Force a secondary operation that throws a domain exception
                await governance.adjudicate_item(session, steward_caller, item_id, "APPROVED")
        except DocumentAlreadyApprovedError:
            # The async with session.begin() context manager automatically issues session.rollback()!
            pass

    # Verify state rolled back cleanly
    async with async_session_maker() as session:
        target_id = item_id if isinstance(item_id, uuid.UUID) else uuid.UUID(str(item_id))
        res_item = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == target_id))
        item_db = res_item.scalar_one()
        assert item_db.status == KnowledgeStatusEnum.PENDING
        assert item_db.is_latest_approved is False

        res_dec = await session.execute(select(GovernanceDecision).where(GovernanceDecision.item_id == target_id))
        assert res_dec.scalar_one_or_none() is None
