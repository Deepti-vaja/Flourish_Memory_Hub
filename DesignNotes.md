# Flourish Governed Memory Hub - Design Notes

**Document Reference**: `AA-FLR-HUB-2026-DN-001`

This document summarizes the core architectural choices and engineering tradeoffs implemented in the Flourish Governed Memory Hub prototype, mapped directly to the enterprise Technical Blueprint.

## 1. Core Component Choices
*   **FastAPI / ASGI**: Chosen for high-throughput, asynchronous concurrency. FastAPI's native Pydantic v2 integration enforces strict schema validation and serialization at the boundary edge, drastically reducing malformed data ingestion.
*   **PostgreSQL 16 + pgvector**: A unified persistence layer eliminates the "split-brain" problem (keeping a relational database in sync with a disparate vector store). PostgreSQL handles both transactional state machines (`PENDING` -> `APPROVED`) and high-performance HNSW vector retrieval simultaneously.
*   **SQLAlchemy 2.0 (Async)**: Modern async ORM provides robust SQL injection protection via parameterized queries and handles connection pooling efficiently for high-scale environments.

## 2. Design Tradeoffs
*   **Monolithic vs. Microservices**: We chose a cohesive modular monolith for the prototype. It eliminates network latency between the ingestion, governance, and audit domains, providing deterministic transactional integrity (`Section 15`). It is structured to be easily decoupled later via Kafka/Redis event streaming if >1,000 req/sec scale is breached (`RSK-06`).
*   **Centralized vs. Distributed Ledger**: Instead of using a complex distributed consensus protocol (e.g., blockchain) for audit immutability, we opted for a centralized, server-side HMAC-SHA256 hash chain (`prev_hash`). This achieves mathematical tamper-evidence without the extreme latency and operational overhead of blockchain nodes (`Section 12`).

## 3. Cryptographic Audit Ledger
The `audit_logs` table forms the backbone of forensic accountability. 
*   **Cryptographic Immutability (Option A)**: Rather than relying solely on database-level role restrictions which can be bypassed by a compromised DBA, this prototype implements cryptographic append-only guarantees. Any `UPDATE` or `DELETE` to historical rows breaks the HMAC-SHA256 hash chain (`prev_hash`).
*   **HMAC Chaining**: Every log row mathematically seals the previous row's signature combined with the current payload using a secret runtime HMAC key. If a malicious DBA bypasses application controls to alter a historical row, the `GET /api/v1/audit/verify` verification engine will immediately detect the broken cryptographic chain in $O(N)$ sequential time.

## 4. Security & Governance Architecture
*   **Fail-Closed Transactions (`Section 15`)**: All endpoints leverage an injected `get_db_transaction()` dependency generator. If any exception occurs during processing, the transaction automatically issues a `ROLLBACK` during the generator's exit phase, guaranteeing zero partial-state corruption.
*   **Zero-Trust Identity (`Section 26.1`)**: Rather than relying on network perimeter trust, the API resolves raw HTTP headers (`X-User-ID`, `X-Functional-Role`, `X-Allowed-Namespaces`) into a strictly parsed, immutable `CallerContext` dataclass.
*   **Least Privilege by Construction**: Retrieval and search operations do not rely on post-query filtering (which is susceptible to leakage). Instead, `CallerContext` parameters (like namespaces and sensitivity ceilings) are deeply embedded into the SQLAlchemy `WHERE` clauses prior to execution, ensuring unauthorized data never leaves the database engine.
