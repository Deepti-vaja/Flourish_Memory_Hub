# Flourish Governed Memory Hub

**Enterprise Reference**: `AA-FLR-HUB-2026-001`

The Flourish Governed Memory Hub is an enterprise-grade, cryptographically audited, and role-scoped organizational knowledge repository designed to serve as the single, authoritative memory layer for autonomous AI agents and human personnel.

## Core Capabilities
1. **Four-Eyes Governance**: Documents ingested from departmental systems of record are held in quarantine (`PENDING` status) until explicitly validated and adjudicated (`APPROVED` or `REJECTED`) by an authorized Domain Steward.
2. **Cryptographic Audit Ledger**: Every state change, ingestion event, governance adjudication, and retrieval attempt is recorded in a tamper-evident, HMAC-SHA256 hash-chained audit log.
3. **Zero-Trust Identity**: Strictly parsed `CallerContext` headers enforce role-based access control and namespace segregation natively at the database layer (preventing application-level data leakage).
4. **Vector & Full-Text Search**: Unified persistence via PostgreSQL 16 and `pgvector` for high-performance HNSW retrieval alongside transactional state machines.

## Architecture & Design
Please refer to the following architectural documents in this repository:
*   [Technical Blueprint](technical-bluprint.md): The exhaustive, single-source-of-truth architecture specification.
*   [Design Notes](DesignNotes.md): A concise summary of the specific engineering tradeoffs, security boundaries, and architectural patterns implemented in the current prototype.

## Quick Start (One-Command Launch)
The system is fully containerized and executes deterministically. It requires **0 manual database seeding steps**.

```bash
# 1. Boot the PostgreSQL database and FastAPI backend
docker compose up --build -d

# 2. Verify system health
curl -f http://localhost:8000/api/v1/status/overview
```

## Interactive Demo Flow
The repository includes a comprehensive, multi-persona demo script that simulates the entire lifecycle of a document (Ingest -> Search -> Adjudicate -> Retrieve -> Audit).

```bash
# Execute the automated workflow
python scripts/demo_flow.py
```
*(Note: Use `python scripts/demo_flow.py --local-test` if you are executing against the ASGI in-memory transport without Docker running).*

## Local Development & Testing
To run the test suite locally using a standard python virtual environment:

```bash
# Install dependencies
python -m venv .venv
source .venv/bin/activate  # (or .venv\Scripts\activate on Windows)
pip install -e .

# Run the full regression & security suite
pytest tests/ -v
```

## Technologies Used
*   **Language**: Python 3.11
*   **Framework**: FastAPI / Uvicorn (ASGI)
*   **Database**: PostgreSQL 16 + pgvector
*   **ORM**: SQLAlchemy 2.0 (Async)
*   **Validation**: Pydantic v2
*   **Migrations**: Alembic
