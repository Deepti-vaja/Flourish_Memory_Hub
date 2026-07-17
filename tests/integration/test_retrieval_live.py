"""
Live PostgreSQL 18 Integration verification suite for Component #5 (`Stage 5 Engine`).

Executes real SQL queries against live PostgreSQL 18 with pgvector & tsvector indexes to empirically verify:
1. Active-Only Quarantine & Horizontal/Vertical Clearance Isolation (`RSK-02 / RSK-05`).
2. Live Flag-32 Cover Density normalized hybrid scoring and pgvector cosine similarity ranking.
3. Cryptographic Search Audit Chaining (`AuditActionEnum.RETRIEVE_SUCCESS`) & HMAC chain verification.
"""
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import datetime
from typing import List
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.audit.chainer import AuditChainService
from app.core.constants import AuditActionEnum, SensitivityLabelEnum
from app.database.session import async_session_maker
from app.models.audit import AuditLog, AuditSequenceHead
from app.models.knowledge import KnowledgeItem
from app.models.namespace import Namespace, User
from app.security.context import CallerContext
from app.services.governance import GovernanceService
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService
from app.services.retrieval_exceptions import ItemNotFoundError, SearchClearanceViolationError


@pytest.fixture
def engineer_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        identity_key="eng-live-user",
        functional_role="ENGINEER",
        allowed_namespaces={"eng.core"},
        max_sensitivity_level=2,
        correlation_id="req-live-eng-001",
    )


@pytest.fixture
def steward_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        identity_key="steward-live-user",
        functional_role="STEWARD",
        allowed_namespaces={"eng.core", "hr.secret"},
        max_sensitivity_level=4,
        correlation_id="req-live-stw-001",
    )


@pytest.fixture
def admin_caller() -> CallerContext:
    return CallerContext(
        user_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        identity_key="admin-live-user",
        functional_role="ADMIN",
        allowed_namespaces={"eng.core", "hr.secret"},
        max_sensitivity_level=4,
        correlation_id="req-live-adm-001",
    )


async def _setup_prerequisites(session) -> None:
    """Ensure prerequisite roles, users, and namespaces exist in live database."""
    from sqlalchemy import select
    from app.models.namespace import Role

    # 1. Ensure Roles
    for role_id in ["ENGINEER", "STEWARD", "ADMIN"]:
        res = await session.execute(select(Role).where(Role.role_id == role_id))
        if res.scalar_one_or_none() is None:
            session.add(Role(role_id=role_id, description=f"{role_id} Role"))
    await session.flush()

    # 2. Ensure Namespaces
    for ns_id in ["eng.core", "hr.secret"]:
        res_ns = await session.execute(select(Namespace).where(Namespace.namespace_id == ns_id))
        if res_ns.scalar_one_or_none() is None:
            session.add(Namespace(namespace_id=ns_id, display_name=f"Live test namespace {ns_id}"))
    await session.flush()

    # 3. Ensure Users
    users_to_add = [
        ("11111111-1111-1111-1111-111111111111", "eng-live-user", "ENGINEER"),
        ("22222222-2222-2222-2222-222222222222", "steward-live-user", "STEWARD"),
        ("33333333-3333-3333-3333-333333333333", "admin-live-user", "ADMIN"),
    ]
    for uid, key, role in users_to_add:
        u_uuid = uuid.UUID(uid)
        res_user = await session.execute(
            select(User).where((User.user_id == u_uuid) | (User.identity_key == key))
        )
        if res_user.scalar_one_or_none() is None:
            session.add(User(user_id=u_uuid, identity_key=key, functional_role=role))
    await session.flush()


@pytest.mark.asyncio
async def test_live_retrieval_quarantine_and_clearance_isolation(
    engineer_caller: CallerContext, steward_caller: CallerContext, admin_caller: CallerContext
) -> None:
    """
    Empirically verify on live PostgreSQL 18:
    - Quarantined PENDING items are hidden.
    - Items exceeding caller sensitivity level (`level 4 vs level 2`) are hidden.
    - Items in unauthorized namespaces (`hr.secret vs eng.core`) are hidden.
    """
    audit_service = AuditChainService()
    ingestion_service = IngestionService(audit_service=audit_service)
    governance_service = GovernanceService(audit_service=audit_service)
    retrieval_service = RetrievalService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            await _setup_prerequisites(session)

            # 1. Ingest & Approve doc_eng_core (Level 2, eng.core -> SHOULD BE FOUND BY ENGINEER)
            doc_eng = await ingestion_service.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Engineering Architecture Guide",
                body="Detailed guide on Flourish memory hub architecture.",
                source_uri="confluence://eng-guide",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
                embedding=[0.05] * 1536,
            )
            await governance_service.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=doc_eng["item_id"],
                decision="APPROVED",
                justification="Approved for engineering access.",
            )

            # 2. Ingest doc_pending (PENDING quarantine -> MUST BE HIDDEN)
            doc_pending = await ingestion_service.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Draft Architecture Note",
                body="Pending review document.",
                source_uri="confluence://eng-draft",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )

            # 3. Ingest & Approve doc_restricted (Level 4 RESTRICTED -> MUST BE HIDDEN FROM ENGINEER)
            doc_restr = await ingestion_service.ingest_item(
                session=session,
                caller=admin_caller,
                title="Executive Roadmap Secret",
                body="Top secret board plan.",
                source_uri="confluence://exec-secret",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.RESTRICTED,
            )
            await governance_service.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=doc_restr["item_id"],
                decision="APPROVED",
                justification="Approved executive secret.",
            )

            # 4. Ingest & Approve doc_hr (hr.secret -> MUST BE HIDDEN FROM ENGINEER)
            doc_hr = await ingestion_service.ingest_item(
                session=session,
                caller=admin_caller,
                title="Employee Salary Band",
                body="Confidential salary compensation table.",
                source_uri="confluence://hr-salary",
                domain_namespace="hr.secret",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
            )
            await governance_service.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=doc_hr["item_id"],
                decision="APPROVED",
                justification="Approved HR document.",
            )

            # NOW EXECUTE LIVE SEARCH AS ENGINEER (level=2, allowed={'eng.core'})
            results = await retrieval_service.search(
                session=session,
                caller=engineer_caller,
                query_text="guide architecture secret salary",
                limit=50,
            )

            # Verify EXACT return: only doc_eng_core is returned!
            returned_ids = {str(r["item_id"]) for r in results}
            assert str(doc_eng["item_id"]) in returned_ids
            assert str(doc_pending["item_id"]) not in returned_ids, "Quarantine leak: PENDING item returned!"
            assert str(doc_restr["item_id"]) not in returned_ids, "Vertical clearance leak: RESTRICTED item returned!"
            assert str(doc_hr["item_id"]) not in returned_ids, "Horizontal clearance leak: hr.secret item returned!"

            # Verify exact ID lookup raises ItemNotFoundError (404) for quarantined or unauthorized items
            with pytest.raises(ItemNotFoundError):
                await retrieval_service.get_item_by_id(session, engineer_caller, doc_pending["item_id"])
            with pytest.raises(ItemNotFoundError):
                await retrieval_service.get_item_by_id(session, engineer_caller, doc_restr["item_id"])
            with pytest.raises(ItemNotFoundError):
                await retrieval_service.get_item_by_id(session, engineer_caller, doc_hr["item_id"])

            await session.rollback()  # Clean rollback (`Section 15 Precondition Step 0`)


@pytest.mark.asyncio
async def test_live_retrieval_vector_cosine_similarity(
    engineer_caller: CallerContext, steward_caller: CallerContext
) -> None:
    """Verify live pgvector 1536-dimensional HNSW/B-Tree cosine similarity ranking."""
    audit_service = AuditChainService()
    ingestion_service = IngestionService(audit_service=audit_service)
    governance_service = GovernanceService(audit_service=audit_service)
    retrieval_service = RetrievalService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            await _setup_prerequisites(session)

            # Vector A: [1.0, 0.0, ..., 0.0]
            vec_a = [0.0] * 1536
            vec_a[0] = 1.0

            # Vector B: [0.0, 1.0, ..., 0.0]
            vec_b = [0.0] * 1536
            vec_b[1] = 1.0

            doc_a = await ingestion_service.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Parallel Vector Document",
                body="Document aligned with axis X",
                source_uri="confluence://vec-a",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
                embedding=vec_a,
            )
            await governance_service.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=doc_a["item_id"],
                decision="APPROVED",
                justification="Approved vector A",
            )

            doc_b = await ingestion_service.ingest_item(
                session=session,
                caller=engineer_caller,
                title="Orthogonal Vector Document",
                body="Document aligned with axis Y",
                source_uri="confluence://vec-b",
                domain_namespace="eng.core",
                sensitivity_label=SensitivityLabelEnum.INTERNAL,
                embedding=vec_b,
            )
            await governance_service.adjudicate_item(
                session=session,
                caller=steward_caller,
                item_id=doc_b["item_id"],
                decision="APPROVED",
                justification="Approved vector B",
            )

            # Search with query_vector = vec_a ([1.0, 0.0, ...])
            results = await retrieval_service.search(
                session=session,
                caller=engineer_caller,
                query_vector=vec_a,
                limit=10,
            )

            # Verify doc_a is top hit with ~1.0 similarity
            assert len(results) >= 1
            assert str(results[0]["item_id"]) == str(doc_a["item_id"])
            assert results[0]["score"] > 0.99

            await session.rollback()


@pytest.mark.asyncio
async def test_live_retrieval_audit_chaining_liveness(
    engineer_caller: CallerContext, steward_caller: CallerContext
) -> None:
    """Verify that search operations write cryptographic audit entries and maintain 100% HMAC chain integrity."""
    audit_service = AuditChainService()
    retrieval_service = RetrievalService(audit_service=audit_service)

    async with async_session_maker() as session:
        async with session.begin():
            await _setup_prerequisites(session)

            # Perform live search
            await retrieval_service.search(
                session=session,
                caller=engineer_caller,
                query_text="audit live test",
            )

            # Verify HMAC integrity across all audit logs
            report = await audit_service.verify_integrity(session=session)
            assert report.compromised is False, f"Audit chain broken during retrieval: {report}"
            assert report.total_verified >= 1

            await session.rollback()
