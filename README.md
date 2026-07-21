---

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16%2B-336791.svg)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-Vector%20Store-4B33AA.svg)](https://github.com/pgvector/pgvector)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![Tests: 85/85 Pass](https://img.shields.io/badge/Tests-85%2F85%20Pass-brightgreen.svg)](tests/)

> **An enterprise-grade, cryptographically audited, and role-scoped organizational knowledge repository. Designed to serve as the single, authoritative memory layer for autonomous AI agents and human personnel with a strict zero-trust governance tollgate.**

---

## 📋 Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Business Motivation](#2-problem-statement--business-motivation)
3. [Key Features](#3-key-features)
4. [System Architecture](#4-system-architecture)
5. [End-to-End Pipeline & Data Flow](#5-end-to-end-pipeline--data-flow)
6. [Repository Architecture](#6-repository-architecture)
7. [Technology Stack](#7-technology-stack)
8. [Installation & Environment Setup](#8-installation--environment-setup)
9. [Quick Start & Demo Instructions](#9-quick-start--demo-instructions)
10. [Governance & Cryptographic Audit Ledger](#10-governance--cryptographic-audit-ledger)
11. [Documentation Reference](#11-documentation-reference)

---

<a name="1-executive-summary"></a>
## 1. Executive Summary
In modern enterprise AI deployments, autonomous agents and human workers require rapid access to cross-departmental institutional knowledge. However, exposing enterprise knowledge directly to AI agents or general search interfaces creates catastrophic operational and legal vulnerabilities. 

This repository implements the **Flourish Governed Memory Hub Prototype** (Ref: `AA-FLR-HUB-2026-001`, Prepared by Binod Kumar), which:
1. **Establishes a Governance Tollgate:** Quarantines ingested documents (`PENDING`) until explicitly validated and adjudicated (`APPROVED`) by an authorized Domain Steward.
2. **Enforces Role-Scoped Retrieval:** Implements Least Privilege by Construction. Queries execute within namespaced and role-scoped SQL execution boundaries, physically eliminating data leakage for unapproved or unauthorized items.
3. **Implements Cryptographic Tamper-Evidence:** Records every state change, ingestion event, and retrieval attempt in an HMAC-SHA256 hash-chained audit log, ensuring absolute tamper-evidence.

---

## 2. Problem Statement & Business Motivation

### 🏢 The Business Risk
An organization deploying AI agents across proprietary data faces two competing pressures:
* **Speed & Autonomy:** Agents must instantly retrieve context to generate code, answer questions, and execute operational workflows.
* **Security & Compliance:** If an AI agent retrieves unverified, outdated, or unauthorized sensitive documents (e.g., `M&A Target Valuations`), it generates harmful hallucinations and leaks data horizontally.

### ⚠️ The Technical Problem
Traditional search engines and vector databases perform post-query filtering. If an index returns a document title or snippet before applying access control checks, sensitive information leaks to unauthorized actors. Furthermore, without a cryptographic ledger, organizations lack the forensic capability to prove *what* knowledge the agent accessed and *who* approved it.

---

<a name="3-key-features"></a>
## 3. Key Features
* **🚫 Zero Leakage Guarantee:** 100% of automated tests confirm that no `PENDING`, `REJECTED`, or out-of-role item is ever returned.
* **🔒 Cryptographic Immutability:** Append-only HMAC-SHA256 hash-chained audit ledger that detects historical row tampering in $O(N)$ sequential time.
* **⚖️ Four-Eyes Governance:** Strict separation of duties preventing an author from approving their own ingested knowledge item.
* **🧠 Unified Vector & Relational Storage:** PostgreSQL 16 with `pgvector` handles both high-performance HNSW vector retrieval and transactional state machines without split-brain sync issues.
* **⚡ Zero-Trust Identity:** Raw HTTP headers are resolved into an immutable `CallerContext`, injecting role-based access directly into SQL `WHERE` clauses prior to execution.

### 🖥️ Application Interfaces

### 📤 1. Document Upload
*Securely upload sensitive documents into the system.*

![Document Upload](assets/upload.png)

### 🔍 2. Active Knowledge Search
*Search for and access only the documents you have permission to view.*

![Active Knowledge Search](assets/search.png)

### ⚖️ 3. Governance Review
*Approve or reject new documents before they become active.*

![Governance Review](assets/governance.png)

### 🛡️ 4. Audit Verification
*Verify that the system's data has not been tampered with.*

![Audit Verification](assets/audit.png)

---

<a name="4-system-architecture"></a>
## 4. System Architecture
The system uses a highly cohesive, modular monolithic design capable of deterministic transactional integrity (`Section 15` fail-closed transactions):

```mermaid
flowchart TB
    subgraph ClientLayer["1. Client Tier (Agents & Humans)"]
        ING["Ingestion Agent"]
        STW["Domain Steward UI"]
        RAG["Retrieval AI Agent"]
    end

    subgraph APILayer["2. API & Middleware (FastAPI)"]
        AUTH["Zero-Trust Identity Middleware"]
        VAL["Pydantic Strict Schema Validation"]
    end

    subgraph ServiceLayer["3. Core Services"]
        ING_SVC["Ingestion Service"]
        GOV_SVC["Governance Service"]
        RET_SVC["Retrieval Service (pgvector)"]
        AUD_SVC["HMAC Audit Chainer"]
    end

    subgraph DataLayer["4. Persistence (PostgreSQL 16)"]
        DOCS["Knowledge Items Table"]
        AUD["Cryptographic Audit Ledger"]
    end

    ING -->|POST /api/v1/ingestion/items| AUTH
    STW -->|POST /api/v1/governance/adjudicate| AUTH
    RAG -->|POST /api/v1/retrieval/search| AUTH
    
    AUTH --> VAL
    VAL --> ING_SVC & GOV_SVC & RET_SVC
    
    ING_SVC --> DOCS & AUD_SVC
    GOV_SVC --> DOCS & AUD_SVC
    RET_SVC --> DOCS & AUD_SVC
    
    AUD_SVC -->|Append Hash Chain| AUD
```

---

<a name="5-end-to-end-pipeline--data-flow"></a>
## 5. End-to-End Pipeline & Data Flow

### 🔄 Data Flow Diagram
The data pipeline transforms raw unstructured intelligence into zero-trust governed embeddings:

```mermaid
flowchart LR
    subgraph Ingestion
        A1["Raw User Input\n(Title, Body, NS)"]
        A2["Metadata & HTTP Headers"]
    end

    subgraph Middleware
        B1["Zero-Trust Resolution\n(CallerContext)"]
        B2["Pydantic Validation"]
    end

    subgraph Engine
        C1["Governance Service\n(Adjudicate PENDING)"]
        C2["Sentence-Transformers Embeddings\n(HuggingFace)"]
        C3["Cryptographic Audit Chainer\n(HMAC-SHA256)"]
    end

    subgraph Storage
        D1["pgvector Index\n(HNSW)"]
        D2["Audit Ledger\n(Append-Only)"]
    end

    A1 --> B1
    A2 --> B1 --> B2 --> C1
    C1 --> C2 --> D1
    B2 --> C3 --> D2
```

### 🕸️ Master Dependency Graph
The execution order enforces strict quality gating: retrieval cannot proceed without governance adjudication, and no transaction commits without a valid cryptographic audit seal.

```text
[Raw Ingestion Request]
          ↓
[Zero-Trust Middleware Authentication]
          ↓
[Pydantic strict typing validation]
          ↓
[Database Transaction Start (Asyncpg)]
          ↓
[Document inserted as PENDING] ---> (Retrieval BLOCKED)
          ↓
[HMAC Audit Sequence Signed]
          ↓
[Transaction Commit]
          ↓
[Steward Adjudicates to APPROVED] ---> (Retrieval UNLOCKED)
```

---

<a name="6-repository-architecture"></a>
## 6. Repository Architecture

The codebase is organized into an enterprise-ready modular monolith architecture, separating configuration, API endpoints, core services, and frontend assets:

```text
Flourish_Memory_Hub/
├── README.md                         # Definitive project documentation & executive guides
├── Flourish_Memory_Hub_Prototype_Brief.docx # Architecture specification
├── pyproject.toml                    # Standardized Python dependencies and build config
├── docker-compose.yml                # Master production orchestration
├── docker-compose-qa.yml             # Ephemeral QA testing orchestration
│
├── app/                              # Core Application Code
│   ├── main.py                       # FastAPI ASGI entrypoint & frontend static mount
│   ├── api/                          # API Router Layer
│   │   ├── deps.py                   # FastAPI dependency injection (Auth & DB Sessions)
│   │   └── v1/endpoints/             # Controllers: ingestion.py, governance.py, retrieval.py
│   ├── core/                         # Configuration & Secrets Management
│   ├── models/                       # SQLAlchemy Database Definitions
│   │   ├── base.py                   # Declarative Base
│   │   ├── namespace.py              # Knowledge Items & pgvector models
│   │   └── audit.py                  # Cryptographic ledger models
│   ├── schemas/                      # Pydantic Request/Response DTOs
│   ├── security/                     # Authorization & Zero-Trust logic
│   └── services/                     # Business Logic Layer
│       ├── ingestion.py              # Document processing & embedding generation
│       ├── governance.py             # Four-Eyes approval logic
│       └── retrieval.py              # Hybrid pgvector search engine
│   └── audit/
│       └── chainer.py                # HMAC-SHA256 cryptographic sequence logic
│
├── frontend/                         # Vanilla JS / HTML / CSS Client Application
│   ├── index.html                    # Single-page application structure
│   ├── app.js                        # API integration and dynamic DOM manipulation
│   └── styles.css                    # Glassmorphic and responsive styling
│
├── scripts/                          # Utilities & Demo Orchestration
│   └── demo_flow.py                  # CLI end-to-end persona demonstration
│
└── tests/                            # Automated Regression Suite
    ├── conftest.py                   # Pytest fixtures and async DB test engine
    ├── test_api_ingestion.py         # End-to-end ingestion tests
    └── test_audit_integrity.py       # Cryptographic tamper-evidence tests
```

---

<a name="7-technology-stack"></a>
## 7. Technology Stack
* **Language:** Python 3.11
* **Framework:** FastAPI / Uvicorn (ASGI)
* **Database:** PostgreSQL 16 + pgvector
* **ORM:** SQLAlchemy 2.0 (Async)
* **Validation:** Pydantic v2
* **Migrations:** Alembic
* **Orchestration:** Docker Compose

---

<a name="8-installation--environment-setup"></a>
## 8. Installation & Environment Setup
The system is fully containerized and executes deterministically. It requires **0 manual database seeding steps**.

```bash
# 1. Clone the repository
git clone <repository_url>
cd Flourish_Memory_Hub

# 2. Boot the PostgreSQL database and FastAPI backend
docker compose up --build -d

# 3. Verify system health
curl -f http://localhost:8000/api/v1/status/overview
```

To run the test suite locally using a standard Python virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # (or .venv\Scripts\activate on Windows)
pip install -e .
pytest tests/ -v
```

---

<a name="9-quick-start--demo-instructions"></a>
## 9. Quick Start & Demo Instructions
The repository includes a comprehensive, multi-persona demo script that simulates the entire lifecycle of a document in an interactive CLI. 

```bash
# Execute the automated multi-persona workflow
python scripts/demo_flow.py
```
*(Note: Use `python scripts/demo_flow.py --local-test` if you are executing against the ASGI in-memory transport without Docker running).*

### 💻 Verbatim CLI Demo Transcript
```text
Flourish Memory Hub - Interactive Demo Flow

--- STEP 1: ENGINEER INGESTS DOCUMENT ---
POST /api/v1/ingestion/items
Success! Item ID: a5c68325-17c8-4342-bc72-25832012bc6a | Status: PENDING

--- STEP 2: ENGINEER ATTEMPTS SEARCH (PENDING) ---
POST /api/v1/retrieval/search
Item found in search? False (Expected: False because it is PENDING)

--- STEP 3: STEWARD APPROVES DOCUMENT ---
POST /api/v1/governance/adjudicate/a5c68325-17c8-4342-bc72-25832012bc6a
Success! New Status: APPROVED

--- STEP 4: ENGINEER GENERATES LLM CONTEXT ---
POST /api/v1/context/assemble
Success! Generated XML Prompt Length: 579 chars
Manifest contains 2 citations.

--- STEP 5: ADMIN VERIFIES CRYPTOGRAPHIC LEDGER ---
GET /api/v1/audit/verify
Success! Compromised: False | Verified Records: 5

*** DEMO WORKFLOW COMPLETED SUCCESSFULLY ***
```

---

<a name="10-governance--cryptographic-audit-ledger"></a>
## 10. Governance & Cryptographic Audit Ledger
To ensure forensic accountability, the `audit_logs` table forms the backbone of the memory hub:
* **Cryptographic Immutability (Option A):** Rather than relying solely on database-level role restrictions which can be bypassed by a compromised DBA, this prototype implements cryptographic append-only guarantees. 
* **HMAC Chaining:** Every log row mathematically seals the previous row's signature combined with the current payload using a secret runtime HMAC key (`prev_hash`). Any `UPDATE` or `DELETE` to historical rows breaks the chain and triggers an immediate compromise alert via `/api/v1/audit/verify`.

---

<a name="11-documentation-reference"></a>
## 11. Documentation Reference
For exhaustive architectural specifications, refer to the following project deliverables:
* [Flourish_Memory_Hub](Flourish_Memory_Hub_Prototype_Brief.docx): The single-source-of-truth enterprise architecture specification.
* [Design Notes](DesignNotes.md): A concise summary of the specific engineering tradeoffs, security boundaries, and architectural patterns implemented in this prototype.
