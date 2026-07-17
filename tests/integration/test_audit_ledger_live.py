r"""
Flourish Governed Memory Hub - Live Integration Tests for Cryptographic Audit Ledger
Executes directly against the live PostgreSQL 18 instance (`flourish_memory_hub`).
Verifies:
  1. TC-SEC-004: Sequential chaining liveness (`seq 1 -> 2 -> 3`), HMAC verification, and head advancement.
  2. TC-SEC-005: Tamper detection rate (100% detection when historical rows are mutated via SQL).
  3. Concurrency serialization: Single-row locking (`FOR UPDATE WHERE lock_key = 1`) under concurrent tasks (`RSK-01`).
  4. Shared transaction boundaries & atomic rollback guarantees (`Section 15`).
"""

import asyncio
import sys
import uuid
import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

# On Windows, psycopg3 AsyncConnection requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.constants import AuditActionEnum
from app.database.session import async_session_maker
from app.models.audit import AuditLog, AuditSequenceHead
from app.models.namespace import Role, User
from app.audit import (
    AuditChainService,
    AuditEventPayload,
    AuditVerifyResult,
)

# Shared test secret key
TEST_SECRET = b"live-integration-hmac-secret-key-2026"
SYSTEM_USER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture(autouse=True)
async def reset_audit_ledger_state() -> None:
    """
    Fixture ensuring the database starts and ends cleanly for each test.
    1. Ensures SYSTEM role and SYSTEM user exist in database for `actor_id` FK checks (`fk_audit_logs_actor_id_users`).
    2. Resets `audit_logs` table and sets `audit_sequence_head` to 0 / 64 zeros.
    """
    async with async_session_maker() as session:
        # Ensure SYSTEM role exists
        res_role = await session.execute(select(Role).where(Role.role_id == "SYSTEM"))
        if res_role.scalar_one_or_none() is None:
            session.add(Role(role_id="SYSTEM", description="System Bootstrap Role"))
            await session.flush()

        # Ensure SYSTEM user exists for bootstrap audit logs
        res_user = await session.execute(select(User).where(User.user_id == SYSTEM_USER_UUID))
        if res_user.scalar_one_or_none() is None:
            session.add(
                User(
                    user_id=SYSTEM_USER_UUID,
                    identity_key="system@flourish.ai",
                    functional_role="SYSTEM",
                )
            )
            await session.flush()

        # Clean ledger tables
        await session.execute(delete(AuditLog))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()

    yield

    async with async_session_maker() as session:
        await session.execute(delete(AuditLog))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_tc_sec_004_sequential_chaining_liveness() -> None:
    """
    Verify `TC-SEC-004`: Appending 3 sequential events strictly increments `sequence_id`,
    computes accurate HMAC SHA-256 signatures linking to `prev_hash`, advances `audit_sequence_head`,
    and passes O(N) `verify_integrity()` without errors.
    """
    service = AuditChainService(secret_key=TEST_SECRET)
    async with async_session_maker() as session:
        # Event 1: Ingest
        payload_1 = AuditEventPayload(
            action_type=AuditActionEnum.INGEST,
            actor_id=None,  # System bootstrap
            target_id=None,
            details={"source": "pytest-liveness-1"},
        )
        seq_1 = await service.log_event(session, payload_1)
        assert seq_1 == 1

        # Event 2: Approve
        payload_2 = AuditEventPayload(
            action_type=AuditActionEnum.APPROVE,
            actor_id=None,
            target_id=None,
            details={"decision": "APPROVED"},
        )
        seq_2 = await service.log_event(session, payload_2)
        assert seq_2 == 2

        # Event 3: Retrieve Success
        payload_3 = AuditEventPayload(
            action_type=AuditActionEnum.RETRIEVE_SUCCESS,
            actor_id=None,
            target_id=None,
            details={"query_hash": "abc123hash"},
        )
        seq_3 = await service.log_event(session, payload_3)
        assert seq_3 == 3

        # Verify audit_sequence_head row directly from database
        stmt_head = select(AuditSequenceHead).where(AuditSequenceHead.lock_key == 1)
        res_head = await session.execute(stmt_head)
        head = res_head.scalar_one()
        assert head.last_sequence_id == 3
        assert len(head.last_entry_hash) == 64

        # Verify last row entry_hash exactly matches head pointer
        stmt_last = select(AuditLog).where(AuditLog.sequence_id == 3)
        res_last = await session.execute(stmt_last)
        last_log = res_last.scalar_one()
        assert last_log.entry_hash == head.last_entry_hash

        # Perform full O(N) chain verification
        verification: AuditVerifyResult = await service.verify_integrity(
            session, secret_key=TEST_SECRET
        )
        assert verification.compromised is False
        assert verification.total_verified == 3
        assert verification.broken_sequence_id is None
        assert "Integrity verified" in str(verification.reason)


@pytest.mark.asyncio
async def test_tc_sec_005_tamper_detection_on_row_mutation() -> None:
    r"""
    Verify `TC-SEC-005`: If any historical row (`details_json`, `actor_id`, `action_type`, or `entry_hash`)
    is mutated via raw SQL after insertion, `verify_integrity()` catches the tamper with 100% precision.
    """
    service = AuditChainService(secret_key=TEST_SECRET)
    async with async_session_maker() as session:
        # Append 3 valid events
        for idx in range(1, 4):
            await service.log_event(
                session,
                AuditEventPayload(
                    action_type=AuditActionEnum.INGEST,
                    actor_id=None,
                    target_id=None,
                    details={"batch": idx},
                ),
            )
        await session.flush()

        # Execute unauthorized post-facto SQL mutation on sequence_id = 2 (`details_json` altered)
        await session.execute(
            text("UPDATE audit_logs SET details_json = '{\"batch\": 999}' WHERE sequence_id = 2;")
        )
        await session.flush()

        # Run verification check
        result = await service.verify_integrity(session, secret_key=TEST_SECRET)
        assert result.compromised is True
        assert result.broken_sequence_id == 2
        assert "Signature Mismatch" in str(result.reason)


@pytest.mark.asyncio
async def test_concurrency_lock_serialization_rsk01() -> None:
    """
    Verify single-row pessimistic locking (`SELECT ... FOR UPDATE WHERE lock_key = 1`) (`RSK-01`).
    Five concurrent tasks executing separate transactions simultaneously must serialize cleanly,
    producing exact sequence progression (1..5) with zero unique key violations or deadlocks.
    """
    service = AuditChainService(secret_key=TEST_SECRET)

    async def _worker(worker_id: int) -> int:
        async with async_session_maker() as session:
            payload = AuditEventPayload(
                action_type=AuditActionEnum.INGEST,
                actor_id=None,
                target_id=None,
                details={"worker": worker_id},
            )
            seq = await service.log_event(session, payload)
            await session.commit()
            return seq

    # Launch 5 concurrent workers simultaneously
    tasks = [_worker(i) for i in range(1, 6)]
    results = await asyncio.gather(*tasks)

    # Sort generated sequence IDs
    sorted_seqs = sorted(results)
    assert sorted_seqs == [1, 2, 3, 4, 5]

    # Verify entire chain integrity after concurrent writes
    async with async_session_maker() as session:
        verification = await service.verify_integrity(session, secret_key=TEST_SECRET)
        assert verification.compromised is False
        assert verification.total_verified == 5


@pytest.mark.asyncio
async def test_transaction_rollback_guarantee_sec15() -> None:
    """
    Verify shared transaction boundary (`Section 15`). If a caller rolls back (`session.rollback()`)
    after `log_event()`, both the appended `AuditLog` row and the sequence head update revert cleanly.
    """
    service = AuditChainService(secret_key=TEST_SECRET)
    async with async_session_maker() as session:
        payload = AuditEventPayload(
            action_type=AuditActionEnum.INGEST,
            actor_id=None,
            target_id=None,
            details={"transient": True},
        )
        seq = await service.log_event(session, payload)
        assert seq == 1

        # Check head before rollback inside same transaction
        res = await session.execute(select(AuditSequenceHead).where(AuditSequenceHead.lock_key == 1))
        assert res.scalar_one().last_sequence_id == 1

        # Simulate parent business failure and rollback
        await session.rollback()

    # Verify state after rollback inside a new session
    async with async_session_maker() as session:
        res_head = await session.execute(
            select(AuditSequenceHead).where(AuditSequenceHead.lock_key == 1)
        )
        head = res_head.scalar_one()
        assert head.last_sequence_id == 0
        assert head.last_entry_hash == ("0" * 64)

        res_logs = await session.execute(select(AuditLog))
        assert res_logs.scalars().first() is None


@pytest.mark.asyncio
async def test_issue_low_02_verify_integrity_cursor_cleanup_on_early_exit() -> None:
    """
    Verify `ISSUE-LOW-02`: When `verify_integrity()` exits prematurely due to a detected
    tamper (`compromised=True`), the streaming cursor is explicitly closed via `await stream.aclose()`,
    allowing the exact same `AsyncSession` object to execute subsequent queries cleanly.
    """
    service = AuditChainService(secret_key=TEST_SECRET)
    async with async_session_maker() as session:
        # Append 3 valid events
        for idx in range(1, 4):
            await service.log_event(
                session,
                AuditEventPayload(
                    action_type=AuditActionEnum.INGEST,
                    actor_id=None,
                    target_id=None,
                    details={"batch": idx},
                ),
            )
        await session.flush()

        # Mutate sequence_id = 2 to force verify_integrity to return early after row 2
        await session.execute(
            text("UPDATE audit_logs SET details_json = '{\"batch\": 888}' WHERE sequence_id = 2;")
        )
        await session.flush()

        # 1st verification call: exits early (`compromised=True` on sequence_id=2)
        result_1 = await service.verify_integrity(session, secret_key=TEST_SECRET)
        assert result_1.compromised is True
        assert result_1.broken_sequence_id == 2

        # 2nd verification call immediately on the same session: must succeed without cursor conflict
        result_2 = await service.verify_integrity(session, secret_key=TEST_SECRET)
        assert result_2.compromised is True
        assert result_2.broken_sequence_id == 2
