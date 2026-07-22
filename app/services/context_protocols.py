"""
Context Assembly Service Protocol Definition (`Stage 6 Engine`).

Mandated by Blueprint Section 26.6 (ContextAssemblyServiceProtocol), Section 13 (Active-Only Gating),
and Section 19 (RSK-04 / RSK-05). Strictly decoupled from concrete implementation (`Option A Immutability`).
"""

import uuid
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from app.security.context import CallerContext


@runtime_checkable
class ContextAssemblyServiceProtocol(Protocol):
    """
    Contract for Stage 6 Context Assembly, Lineage Tracing & Prompt Injection Defense Engine.

    All implementations must guarantee:
    1. Precondition Step 0 (`session.in_transaction() must be True / zero lifecycle commits`).
    2. Multi-channel Orchestration (`explicit_item_ids` exact lookup via `get_item_by_id` + semantic `search`).
    3. 3-Stage Prompt Injection Defense (`NFKC canonicalization, XML/CDTA structural escaping, active breakout interception`).
    4. Atomic Token & Character Budget Packing (`never half-truncating items; deducting 256 system + 45 citation reserves`).
    5. Traceable 2-Hop Cryptographic Audit Chaining (`STAGE_6_CONTEXT_ASSEMBLY` vs `STAGE_5_RETRIEVAL` demarcation).
    """

    async def assemble_context(
        self,
        session: Any,
        caller: CallerContext,
        query_text: str | None = None,
        query_vector: list[float] | None = None,
        explicit_item_ids: list[str | uuid.UUID] | None = None,
        max_tokens: int = 4096,
        similarity_threshold: float = 0.7,
        domain_namespaces: list[str] | None = None,
        enable_injection_defense: bool = True,
        strict_security_abort: bool = False,
        tokenizer_fn: Callable[[str], int] | None = None,
    ) -> dict[str, Any]:
        """
        Execute clearance-scoped retrieval and assemble a sanitized, lineage-tracked LLM context block.

        Args:
            session: Active AsyncSession within caller-owned transaction boundary.
            caller: Authenticated CallerContext identity with namespace/sensitivity clearances.
            query_text: Optional natural language query for hybrid lexical Cover Density search.
            query_vector: Optional 1536-dimensional float vector for semantic similarity.
            explicit_item_ids: Optional list of deterministic document UUIDs to pack first (`e.g., regulatory citations`).
            max_tokens: Total token ceiling (`default 4096`).
            similarity_threshold: Minimum vector similarity threshold (`0.0 to 1.0`).
            domain_namespaces: Optional subset of namespaces (`must be subset of caller.allowed_namespaces`).
            enable_injection_defense: Whether to execute 3-Stage NFKC/XML/Heuristic sanitization (`default True`).
            strict_security_abort: If True, raises PromptInjectionSecurityError upon discovering breakout injection instead of graceful skipping (`default False`).
            tokenizer_fn: Optional custom tokenizer callback `Callable[[str], int]`. If None, uses conservative 2.8 chars/token math.

        Returns:
            Zero-copy DTO dictionary containing:
            - 'assembled_prompt': str (Formatted XML citations ready for LLM prompt injection)
            - 'lineage_manifest': List[Dict[str, Any]] (Exact document IDs, versions, namespaces, scores, and SHA256 content hashes)
            - 'tokens_used': int (Estimated total token consumption including reserves)
            - 'items_included': int (Number of items successfully packed)
            - 'items_rejected_injection': int (Number of items skipped due to prompt injection breakout check)
            - 'items_omitted_budget': int (Number of valid items omitted because they exceeded remaining budget)
            - 'items_omitted_clearance': int (Number of explicit_item_ids omitted or not found due to clearance boundaries)
        """
        ...
