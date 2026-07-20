"""
Flourish Governed Memory Hub - Security Test for Audit Truncation Detection

Executes raw SQL DELETE FROM audit_logs WHERE sequence_id = <latest_sequence_id>
Calls GET /api/v1/audit/verify and asserts response is compromised (Ledger Truncated).
"""
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import uuid
import httpx
import pytest
from sqlalchemy import delete, select, text, update
from httpx import AsyncClient, ASGITransport

from app.database.session import async_session_maker
from app.main import app
from app.models.audit import AuditLog, AuditSequenceHead
from app.models.namespace import Role, User
from app.audit.chainer import AuditChainService
from app.core.constants import AuditActionEnum
from app.audit import AuditEventPayload

SYSTEM_USER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

@pytest.fixture(autouse=True)
async def reset_audit_ledger_state() -> None:
    """Ensure a clean audit ledger state before testing."""
    async with async_session_maker() as session:
        # Ensure SYSTEM role exists
        res_role = await session.execute(select(Role).where(Role.role_id == "SYSTEM"))
        if res_role.scalar_one_or_none() is None:
            session.add(Role(role_id="SYSTEM", description="System Bootstrap Role"))
            await session.flush()

        # Ensure SYSTEM user exists
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

        # Reset audit tables
        await session.execute(delete(AuditLog))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()
        
    yield
    
    # Teardown
    async with async_session_maker() as session:
        await session.execute(delete(AuditLog))
        await session.execute(
            update(AuditSequenceHead)
            .where(AuditSequenceHead.lock_key == 1)
            .values(last_sequence_id=0, last_entry_hash="0" * 64)
        )
        await session.commit()

@pytest.mark.asyncio
async def test_audit_truncation_detection_api() -> None:
    from app.core.config import settings
    app_secret = settings.AUDIT_HMAC_SECRET.encode("utf-8")
    
    service = AuditChainService(secret_key=app_secret)
    async with async_session_maker() as session:
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
        await session.commit()

    admin_headers = {
        "Authorization": "Bearer admin_token",
        "X-User-Id": "33333333-3333-3333-3333-333333333333",
        "X-User-Role": "ADMIN",
        "X-Allowed-Namespaces": "*"
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_pre = await client.get("/api/v1/audit/verify", headers=admin_headers)
        assert res_pre.status_code == 200
        data_pre = res_pre.json()
        assert data_pre["compromised"] is False
        assert data_pre["verified_records"] == 3

    # Simulate truncation attack: delete the last row
    async with async_session_maker() as session:
        await session.execute(
            text("DELETE FROM audit_logs WHERE sequence_id = (SELECT MAX(sequence_id) FROM audit_logs)")
        )
        await session.commit()

    # Call verification API (after truncation, should fail)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_post = await client.get("/api/v1/audit/verify", headers=admin_headers)
        assert res_post.status_code == 200
        data_post = res_post.json()
        
        assert data_post["compromised"] is True
        assert "Ledger Truncated" in str(data_post.get("message", ""))
        assert data_post["verified_records"] == 2
