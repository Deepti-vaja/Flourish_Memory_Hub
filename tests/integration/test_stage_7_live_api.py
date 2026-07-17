"""
Live PostgreSQL 18 End-to-End Integration Verification for Component #7 (`Stage 7 API & Middleware`).
Empirically tests the entire multi-actor HTTP lifecycle across all 5 REST controllers against our real database:
  1. POST /api/v1/ingestion/items (Engineer -> 201 Created PENDING)
  2. POST /api/v1/governance/adjudicate/{item_id} (Steward -> 200 OK ACTIVE)
  3. POST /api/v1/retrieval/search (Engineer -> 200 OK Hybrid Hits)
  4. GET /api/v1/retrieval/items/{item_id} (Engineer -> 200 OK Item DTO)
  5. POST /api/v1/context/assemble (Engineer -> 200 OK XML Prompt Block + Manifest)
  6. GET /api/v1/audit/verify (Admin -> 200 OK Cryptographic Ledger Integrity)
"""
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import uuid
import httpx
import pytest
from sqlalchemy import select
from app.database.session import async_session_maker
from app.main import app
from app.models.namespace import Namespace, Role, User


async def _setup_prerequisites() -> None:
    """Ensure roles, namespaces, and users exist in live PostgreSQL database before testing."""
    async with async_session_maker() as session:
        async with session.begin():
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
                ("11111111-1111-1111-1111-111111111111", "eng-api-user", "ENGINEER"),
                ("22222222-2222-2222-2222-222222222222", "steward-api-user", "STEWARD"),
                ("33333333-3333-3333-3333-333333333333", "admin-api-user", "ADMIN"),
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
async def test_stage_7_live_http_end_to_end_lifecycle():
    await _setup_prerequisites()

    engineer_headers = {
        "X-User-ID": "11111111-1111-1111-1111-111111111111",
        "X-Identity-Key": "eng-api-user",
        "X-Functional-Role": "ENGINEER",
        "X-Allowed-Namespaces": "eng.core, hr.secret",
        "X-Sensitivity-Ceiling": "3",
        "X-Request-ID": f"req-api-eng-{uuid.uuid4().hex[:8]}"
    }

    steward_headers = {
        "X-User-ID": "22222222-2222-2222-2222-222222222222",
        "X-Identity-Key": "steward-api-user",
        "X-Functional-Role": "STEWARD",
        "X-Allowed-Namespaces": "eng.core, hr.secret",
        "X-Sensitivity-Ceiling": "4",
        "X-Request-ID": f"req-api-stw-{uuid.uuid4().hex[:8]}"
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: POST /api/v1/ingestion/items (`as Engineer -> 201 Created PENDING`)
        ingest_payload = {
            "title": f"Live Stage 7 Architecture Guide {uuid.uuid4().hex[:6]}",
            "body": "Stage 7 enforces Section 15 transaction safety and Section 26.1 caller context isolation over REST APIs.",
            "namespace": "eng.core",
            "sensitivity_level": 2,
            "source_uri": "https://flourish.corp/docs/stage7"
        }
        res_ingest = await client.post("/api/v1/ingestion/items", json=ingest_payload, headers=engineer_headers)
        assert res_ingest.status_code == 201, f"Ingestion failed: {res_ingest.text}"
        ingest_data = res_ingest.json()
        assert "item_id" in ingest_data
        assert ingest_data["status"] == "PENDING"
        item_id = ingest_data["item_id"]

        # Step 2: POST /api/v1/retrieval/search (`as Engineer while PENDING -> should NOT find PENDING item`)
        res_search_pending = await client.post(
            "/api/v1/retrieval/search",
            json={"query": "Stage 7 enforces Section 15", "top_k": 5},
            headers=engineer_headers
        )
        assert res_search_pending.status_code == 200
        assert all(hit["item_id"] != item_id for hit in res_search_pending.json())

        # Step 3: POST /api/v1/governance/adjudicate/{item_id} (`as Steward -> 200 OK ACTIVE/APPROVED`)
        adjudicate_payload = {
            "action": "approve",
            "justification": "Four-Eyes review completed successfully by Stage 7 Data Steward."
        }
        res_adjudicate = await client.post(
            f"/api/v1/governance/adjudicate/{item_id}",
            json=adjudicate_payload,
            headers=steward_headers
        )
        assert res_adjudicate.status_code == 200, f"Adjudication failed: {res_adjudicate.text}"
        adjudicate_data = res_adjudicate.json()
        assert adjudicate_data["item_id"] == item_id
        assert adjudicate_data["status"] in ("ACTIVE", "APPROVED")

        # Step 4: POST /api/v1/retrieval/search (`as Engineer after approval -> 200 OK finds active item`)
        res_search_active = await client.post(
            "/api/v1/retrieval/search",
            json={"query": "Stage 7 enforces Section 15", "top_k": 5},
            headers=engineer_headers
        )
        assert res_search_active.status_code == 200, f"Search failed: {res_search_active.text}"
        hits = res_search_active.json()
        assert any(hit["item_id"] == item_id for hit in hits), f"Item {item_id} not found in search hits: {hits}"

        # Step 5: GET /api/v1/retrieval/items/{item_id} (`as Engineer -> 200 OK exact DTO`)
        res_get_item = await client.get(f"/api/v1/retrieval/items/{item_id}", headers=engineer_headers)
        assert res_get_item.status_code == 200, f"Get item failed: {res_get_item.text}"
        item_dto = res_get_item.json()
        assert item_dto["item_id"] == item_id
        assert item_dto["title"] == ingest_payload["title"]

        # Step 6: POST /api/v1/context/assemble (`as Engineer -> 200 OK XML Prompt + Lineage Manifest`)
        context_payload = {
            "query": "Stage 7 enforces Section 15",
            "max_tokens": 4096
        }
        res_context = await client.post("/api/v1/context/assemble", json=context_payload, headers=engineer_headers)
        assert res_context.status_code == 200, f"Context assembly failed: {res_context.text}"
        context_data = res_context.json()
        assert "assembled_prompt" in context_data
        assert "manifest" in context_data
        assert len(context_data["manifest"]) > 0
        assert any(entry["item_id"] == item_id for entry in context_data["manifest"])

        # Step 7: GET /api/v1/audit/verify (`as Admin -> 200 OK cryptographic ledger verification`)
        res_audit = await client.get("/api/v1/audit/verify", headers=steward_headers)
        assert res_audit.status_code == 200, f"Audit verify failed: {res_audit.text}"
        audit_data = res_audit.json()
        assert audit_data["compromised"] is False
        assert audit_data["verified_records"] > 0
