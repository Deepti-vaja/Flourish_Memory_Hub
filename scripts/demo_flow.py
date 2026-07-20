"""
Flourish Memory Hub - Interactive Demo Flow (`Section 6`)
Simulates an end-to-end multi-persona API workflow:
Ingest -> Search (Pending) -> Adjudicate -> Search (Active) -> Context Assemble -> Audit Verify
"""

import asyncio
import sys
import uuid
import httpx

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

API_BASE_URL = "http://localhost:8000"

async def run_demo(use_asgi: bool = False):
    print("Flourish Memory Hub - Interactive Demo Flow")
    
    # 1. Setup Client
    client_kwargs = {"base_url": API_BASE_URL}
    if use_asgi:
        print("Notice: Using in-memory ASGI transport (Local Test Mode)")
        from app.main import app
        client_kwargs["transport"] = httpx.ASGITransport(app=app)
        client_kwargs["base_url"] = "http://test"

    async with httpx.AsyncClient(**client_kwargs) as client:
        # Define persona headers exactly matching app/security/context_resolver.py
        engineer_headers = {
            "X-User-ID": "11111111-1111-1111-1111-111111111111",
            "X-Identity-Key": "eng-api-user",
            "X-Functional-Role": "ENGINEER",
            "X-Allowed-Namespaces": "eng.core, hr.secret",
            "X-Sensitivity-Ceiling": "3",
            "X-Request-ID": f"req-eng-{uuid.uuid4().hex[:8]}"
        }
        
        steward_headers = {
            "X-User-ID": "22222222-2222-2222-2222-222222222222",
            "X-Identity-Key": "steward-api-user",
            "X-Functional-Role": "STEWARD",
            "X-Allowed-Namespaces": "eng.core, hr.secret",
            "X-Sensitivity-Ceiling": "4",
            "X-Request-ID": f"req-stw-{uuid.uuid4().hex[:8]}"
        }
        
        admin_headers = {
            "X-User-ID": "33333333-3333-3333-3333-333333333333",
            "X-Identity-Key": "admin-api-user",
            "X-Functional-Role": "ADMIN",
            "X-Allowed-Namespaces": "*",
            "X-Sensitivity-Ceiling": "4",
            "X-Request-ID": f"req-adm-{uuid.uuid4().hex[:8]}"
        }

        # Step 1: Ingestion
        print("\n--- STEP 1: ENGINEER INGESTS DOCUMENT ---")
        ingest_payload = {
            "title": f"Demo Architecture Guide {uuid.uuid4().hex[:4]}",
            "body": "The memory hub enforces strict Four-Eyes governance and cryptographic audit trails.",
            "namespace": "eng.core",
            "sensitivity_level": 2,
            "source_uri": "https://flourish.corp/docs/demo"
        }
        print(f"POST /api/v1/ingestion/items\nPayload: {ingest_payload}")
        res = await client.post("/api/v1/ingestion/items", json=ingest_payload, headers=engineer_headers)
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
        data = res.json()
        item_id = data["item_id"]
        print(f"Success! Item ID: {item_id} | Status: {data['status']}")

        # Step 2: Attempt Search before approval
        print("\n--- STEP 2: ENGINEER ATTEMPTS SEARCH (PENDING) ---")
        search_payload = {"query": "Four-Eyes governance", "top_k": 5}
        print(f"POST /api/v1/retrieval/search\nPayload: {search_payload}")
        res = await client.post("/api/v1/retrieval/search", json=search_payload, headers=engineer_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        hits = res.json()
        found = any(h["item_id"] == item_id for h in hits)
        print(f"Item found in search? {found} (Expected: False because it is PENDING)")
        assert not found

        # Step 3: Adjudicate
        print("\n--- STEP 3: STEWARD APPROVES DOCUMENT ---")
        adj_payload = {"action": "approve", "justification": "Looks good for demo."}
        print(f"POST /api/v1/governance/adjudicate/{item_id}\nPayload: {adj_payload}")
        res = await client.post(f"/api/v1/governance/adjudicate/{item_id}", json=adj_payload, headers=steward_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        print(f"Success! New Status: {res.json()['status']}")

        # Step 4: Context Assembly
        print("\n--- STEP 4: ENGINEER GENERATES LLM CONTEXT ---")
        ctx_payload = {"query": "governance and cryptographic audit", "max_tokens": 4096}
        print(f"POST /api/v1/context/assemble\nPayload: {ctx_payload}")
        res = await client.post("/api/v1/context/assemble", json=ctx_payload, headers=engineer_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        ctx_data = res.json()
        print(f"Success! Generated XML Prompt Length: {len(ctx_data['assembled_prompt'])} chars")
        print(f"Manifest contains {len(ctx_data['manifest'])} citations.")

        # Step 5: Audit Verification
        print("\n--- STEP 5: ADMIN VERIFIES CRYPTOGRAPHIC LEDGER ---")
        print("GET /api/v1/audit/verify")
        res = await client.get("/api/v1/audit/verify", headers=admin_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        audit_data = res.json()
        print(f"Success! Compromised: {audit_data['compromised']} | Verified Records: {audit_data['verified_records']}")
        
        print("\n*** DEMO WORKFLOW COMPLETED SUCCESSFULLY ***")

if __name__ == "__main__":
    use_asgi = "--local-test" in sys.argv
    asyncio.run(run_demo(use_asgi=use_asgi))

