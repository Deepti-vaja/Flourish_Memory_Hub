r"""
Flourish Governed Memory Hub - Live Integration Test Suite for Component #3 (`IngestionService`)
Executes directly against the live PostgreSQL 18 instance (`flourish_memory_hub`).
Verifies:
  1. Blue-Green quarantine isolation & versioning (`RSK-05`, `REQ-CORE-002`).
  2. 64-bit Composite Advisory Transaction Locking (`pg_advisory_xact_lock`) under parallel burst ingestion (`RSK-01`).
  3. Single-transaction atomicity & Fail-Closed rollback guarantees (`RSK-06`, `Section 15`).
  4. Server-computed `TSVECTOR` lexeme generation & 1536-dim vector embedding persistence (`RSK-07`).
"""

import asyncio
import sys
from typing import Any
import uuid
import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

# On Windows, psycopg3 AsyncConnection requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.audit import AuditChainService
from app.audit.exceptions import AuditConcurrencyError
from app.core.constants import KnowledgeStatusEnum, SensitivityLabelEnum
from app.database.session import async_session_maker
from app.models.audit import AuditLog, AuditSequenceHead
from app.models.governance import GovernanceDecision
from app.models.knowledge import KnowledgeItem
from app.models.namespace import Namespace, Role, User
from app.security.context import CallerContext
from app.services import IngestionService


TEST_SECRET = b"live-integration-hmac-secret-key-2026"
TEST_USER_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
async def reset_ingestion_state() -> None:
    """
    Ensures clean database state before and after each integration test:
    1. Ensures SYSTEM/ENGINEER roles, users, and `test.ns` namespace exist.
    2. Cleans `knowledge_items` and `audit_logs`, resetting `audit_sequence_head` to 0.
    """
    async with async_session_maker() as session:
        # Ensure Roles exist
        for role_id in ["SYSTEM", "ENGINEER"]:
            res = await session.execute(select(Role).where(Role.role_id == role_id))
            if res.scalar_one_or_none() is None:
                session.add(Role(role_id=role_id, description=f"{role_id} Role"))
        await session.flush()

        # Ensure User exists
        res_user = await session.execute(select(User).where(User.user_id == TEST_USER_UUID))
        if res_user.scalar_one_or_none() is None:
            session.add(
                User(
                    user_id=TEST_USER_UUID,
                    identity_key="engineer@flourish.ai",
                    functional_role="ENGINEER",
                )
            )
        await session.flush()

        # Ensure Namespaces exist
        for ns_id in ["test.ns", "test.hr"]:
            res_ns = await session.execute(select(Namespace).where(Namespace.namespace_id == ns_id))
            if res_ns.scalar_one_or_none() is None:
                session.add(
                    Namespace(
                        namespace_id=ns_id,
                        display_name=f"Test Integration Namespace ({ns_id})",
                    )
                )
        await session.flush()

        # Clean data tables
        await session.execute(delete(AuditLog))
        await session.execute(delete(GovernanceDecision))
        await session.execute(delete(KnowledgeItem))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()

    yield

    async with async_session_maker() as session:
        await session.execute(delete(AuditLog))
        await session.execute(delete(GovernanceDecision))
        await session.execute(delete(KnowledgeItem))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()


@pytest.fixture
def test_caller() -> CallerContext:
    return CallerContext(
        user_id=TEST_USER_UUID,
        identity_key="engineer@flourish.ai",
        functional_role="ENGINEER",
        allowed_namespaces={"test.ns", "test.hr"},
        max_sensitivity_level=3,  # CONFIDENTIAL
        correlation_id="test-corr-live-01",
    )


@pytest.mark.asyncio
async def test_blue_green_versioning_and_quarantine_live(test_caller: CallerContext) -> None:
    """
    Verifies Blue-Green ingestion isolation (`RSK-05`):
    1. Ingest Version 1 -> PENDING, is_latest_approved=False.
    2. Promote Version 1 -> APPROVED, is_latest_approved=True (`active Blue version`).
    3. Ingest Version 2 of exact same URI -> PENDING, is_latest_approved=False (`quarantined Green version`).
    4. Verify Version 1 remains undisturbed and active while Version 2 awaits steward review.
    """
    audit_service = AuditChainService(TEST_SECRET)
    service = IngestionService(audit_service)
    uri = "confluence://arch/doc-01"

    # 1. Ingest Version 1
    async with async_session_maker() as session:
        async with session.begin():
            dto_v1 = await service.ingest_item(
                session=session,
                caller=test_caller,
                title="Arch Blueprint V1",
                body="Initial architecture design.",
                source_uri=uri,
                domain_namespace="test.ns",
                sensitivity_label="INTERNAL",
            )
            assert dto_v1["version"] == 1
            assert dto_v1["status"] == "PENDING"
            assert dto_v1["is_latest_approved"] is False

    # 2. Simulate Stage 4 Steward Approval on Version 1
    async with async_session_maker() as session:
        async with session.begin():
            await session.execute(
                update(KnowledgeItem)
                .where(KnowledgeItem.item_id == dto_v1["item_id"])
                .values(status=KnowledgeStatusEnum.APPROVED, is_latest_approved=True)
            )

    # 3. Ingest Version 2 of the same URI
    async with async_session_maker() as session:
        async with session.begin():
            dto_v2 = await service.ingest_item(
                session=session,
                caller=test_caller,
                title="Arch Blueprint V2",
                body="Updated architecture design with Blue-Green engine.",
                source_uri=uri,
                domain_namespace="test.ns",
                sensitivity_label="INTERNAL",
            )
            assert dto_v2["version"] == 2
            assert dto_v2["status"] == "PENDING"
            assert dto_v2["is_latest_approved"] is False

    # 4. Verify DB state directly
    async with async_session_maker() as session:
        res = await session.execute(
            select(KnowledgeItem).where(KnowledgeItem.source_uri == uri).order_by(KnowledgeItem.version.asc())
        )
        rows = res.scalars().all()
        assert len(rows) == 2
        assert rows[0].version == 1 and rows[0].status == KnowledgeStatusEnum.APPROVED and rows[0].is_latest_approved is True
        assert rows[1].version == 2 and rows[1].status == KnowledgeStatusEnum.PENDING and rows[1].is_latest_approved is False


@pytest.mark.asyncio
async def test_pg_advisory_xact_lock_concurrency_live(test_caller: CallerContext) -> None:
    """
    Verifies `pg_advisory_xact_lock` serialization (`RSK-01 / Proposal A`):
    Spawns 5 parallel tasks ingesting the exact same new `source_uri` simultaneously.
    Guarantees zero duplicate `version = 1` inserts and exact sequential versions `1, 2, 3, 4, 5`.
    """
    audit_service = AuditChainService(TEST_SECRET)
    service = IngestionService(audit_service)
    uri = "confluence://parallel/race-doc"

    async def _worker() -> int:
        async with async_session_maker() as session:
            async with session.begin():
                dto = await service.ingest_item(
                    session=session,
                    caller=test_caller,
                    title="Parallel Runbook",
                    body="Stress testing concurrent ingestion locking.",
                    source_uri=uri,
                    domain_namespace="test.ns",
                    sensitivity_label="INTERNAL",
                )
                return dto["version"]

    # Run 5 workers concurrently
    versions = await asyncio.gather(*[_worker() for _ in range(5)])
    assert sorted(versions) == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_atomic_audit_chaining_and_fail_closed_rollback_live(test_caller: CallerContext) -> None:
    """
    Verifies Single-Transaction Atomicity & Fail-Closed SLA (`RSK-06 / Proposal G`):
    If the audit ledger raises an exception during `log_event()`, the entire transaction
    rolls back completely, leaving 0 partial rows in `knowledge_items`.
    """
    audit_service = AuditChainService(TEST_SECRET)
    service = IngestionService(audit_service)

    # 1. Successful ingestion increments sequence_id to 1
    async with async_session_maker() as session:
        async with session.begin():
            dto_ok = await service.ingest_item(
                session=session,
                caller=test_caller,
                title="Valid Runbook",
                body="Should persist successfully.",
                source_uri="confluence://ok-doc",
                domain_namespace="test.ns",
                sensitivity_label="INTERNAL",
            )
            assert dto_ok["audit_sequence_id"] == 1

    # 2. Simulate Audit Ledger Crash during second ingestion
    class _FailingAuditService(AuditChainService):
        async def log_event(self, session: Any, payload: Any) -> int:
            raise AuditConcurrencyError("Simulated Audit Ledger Concurrency Failure")

    failing_service = IngestionService(_FailingAuditService(TEST_SECRET))

    with pytest.raises(AuditConcurrencyError, match="Simulated Audit Ledger Concurrency Failure"):
        async with async_session_maker() as session:
            async with session.begin():
                await failing_service.ingest_item(
                    session=session,
                    caller=test_caller,
                    title="Crashed Runbook",
                    body="Should be rolled back atomically.",
                    source_uri="confluence://fail-doc",
                    domain_namespace="test.ns",
                    sensitivity_label="INTERNAL",
                )

    # 3. Verify exactly 1 row exists in knowledge_items and audit_logs
    async with async_session_maker() as session:
        res_items = await session.execute(select(KnowledgeItem))
        assert len(res_items.scalars().all()) == 1

        res_audit = await session.execute(select(AuditLog))
        assert len(res_audit.scalars().all()) == 1


@pytest.mark.asyncio
async def test_tsvector_and_embedding_persistence_live(test_caller: CallerContext) -> None:
    """
    Verifies server-computed `TSVECTOR` lexeme generation & 1536-dim vector embedding (`RSK-07 / Proposal D`):
    Ensures search_vector contains PostgreSQL stemmer lexemes and embedding array matches exact coordinates.
    """
    audit_service = AuditChainService(TEST_SECRET)
    service = IngestionService(audit_service)
    dummy_vec = [0.05] * 1536

    async with async_session_maker() as session:
        async with session.begin():
            dto = await service.ingest_item(
                session=session,
                caller=test_caller,
                title="Enterprise Kubernetes Runbook",
                body="Verify pod restart policy and horizontal autoscaler configuration.",
                source_uri="confluence://k8s/runbook",
                domain_namespace="test.ns",
                sensitivity_label="CONFIDENTIAL",
                embedding=dummy_vec,
            )

            # Check DTO refreshed values
            assert dto["search_vector"] is not None
            assert "enterpris" in dto["search_vector"] and "kubernet" in dto["search_vector"]
            assert len(dto["embedding"]) == 1536
            assert dto["embedding"][0] == pytest.approx(0.05)

    # Verify directly from database
    async with async_session_maker() as session:
        res = await session.execute(select(KnowledgeItem).where(KnowledgeItem.item_id == dto["item_id"]))
        row = res.scalar_one()
        assert str(row.search_vector) is not None
        assert len(row.embedding) == 1536


@pytest.mark.asyncio
async def test_path_a_global_uri_ownership_live(test_caller: CallerContext) -> None:
    """
    Verifies Path A (`Global URI Namespace Ownership`) directly against live PostgreSQL 18:
    1. Ingest item with source_uri='confluence://path-a-live' into 'test.ns'.
    2. Attempt to ingest same source_uri into 'test.hr'.
    3. Verify IngestionPayloadError is raised immediately (`preventing Stage 4 IntegrityError`).
    """
    audit_service = AuditChainService(TEST_SECRET)
    service = IngestionService(audit_service)
    uri = "confluence://path-a-live"

    # 1. Ingest into test.ns
    async with async_session_maker() as session:
        async with session.begin():
            dto_ns = await service.ingest_item(
                session=session,
                caller=test_caller,
                title="Engineering Runbook",
                body="Valid runbook body.",
                source_uri=uri,
                domain_namespace="test.ns",
                sensitivity_label="INTERNAL",
            )
            assert dto_ns["domain_namespace"] == "test.ns"

    # 2. Attempt cross-namespace ingestion into test.hr
    from app.services.exceptions import IngestionPayloadError
    with pytest.raises(IngestionPayloadError, match="is already registered under namespace 'test.ns'; cannot ingest across different namespaces"):
        async with async_session_maker() as session:
            async with session.begin():
                await service.ingest_item(
                    session=session,
                    caller=test_caller,
                    title="HR Copy of Runbook",
                    body="Should be rejected under Path A.",
                    source_uri=uri,
                    domain_namespace="test.hr",
                    sensitivity_label="INTERNAL",
                )
