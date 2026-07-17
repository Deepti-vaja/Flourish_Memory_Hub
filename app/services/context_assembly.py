"""
Context Assembly, Lineage Tracing & Prompt Injection Defense Engine (`Stage 6 Engine`).

Mandated by Blueprint Section 26.6 (ContextAssemblyServiceProtocol), Section 13 (Active-Only Gating),
and Section 19 (RSK-04 / RSK-05). Implements Option A structural immutability (`zero modifications to #1–#5`).
"""
import html
import hashlib
import re
import unicodedata
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from app.audit.chainer import AuditChainService, AuditEventPayload
from app.core.constants import AuditActionEnum
from app.security.context import CallerContext
from app.services.context_exceptions import (
    ContextAssemblyError,
    LineageIntegrityError,
    PromptInjectionSecurityError,
    TokenBudgetExhaustionError,
)
from app.services.context_protocols import ContextAssemblyServiceProtocol
from app.services.retrieval import RetrievalService
from app.services.retrieval_exceptions import ItemNotFoundError, SearchClearanceViolationError


class ContextAssemblyService(ContextAssemblyServiceProtocol):
    """
    Core implementation of the Stage 6 Context Assembly & Lineage Engine.
    
    Guarantees:
    1. Precondition Step 0 (`session.in_transaction() must be True / zero lifecycle commits`).
    2. Multi-channel Orchestration (`explicit_item_ids` exact lookup via `RetrievalService.get_item_by_id` + `search`).
    3. 3-Stage Prompt Injection Defense:
       - Stage 1: NFKC canonicalization + stripping zero-width joiners (`\\u200b`, `\\ufeff`, `\\x00`-`\\x1f`).
       - Stage 2: Active threat interception against wrapper breakouts and system overrides.
       - Stage 3: Structural XML/CDTA escaping (`&lt;|im_start|&gt;`) inside `<knowledge_citation ...>`.
    4. Atomic Token & Character Budgeting:
       - Reserves `SYSTEM_FRAME_RESERVE = 256` and `CITATION_OVERHEAD_PER_ITEM = 45`.
       - Pluggable `tokenizer_fn` callback or conservative `2.8 chars/token` math.
       - Never half-truncates; omits items when `current_tokens + item_tokens > effective_budget`.
    5. Traceable 2-Hop Cryptographic Audit Chaining (`AuditActionEnum.RETRIEVE_SUCCESS` with `stage='STAGE_6_CONTEXT_ASSEMBLY'`).
    """

    SYSTEM_FRAME_RESERVE = 256
    CITATION_OVERHEAD_PER_ITEM = 45

    # Active threat breakout patterns caught after NFKC normalization
    BREAKOUT_PATTERNS = [
        re.compile(r"</\s*knowledge_citation\s*>", re.IGNORECASE),
        re.compile(r"<\s*knowledge_citation[^>]*>", re.IGNORECASE),
        re.compile(r"SYSTEM\s+OVERRIDE\s*:", re.IGNORECASE),
        re.compile(r"IGNORE\s+ALL\s+(PREVIOUS\s+)?(INSTRUCTIONS|RULES|PROMPTS)", re.IGNORECASE),
    ]

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        audit_service: Optional[AuditChainService] = None,
    ) -> None:
        self.retrieval_service = retrieval_service or RetrievalService()
        self.audit_service = audit_service or AuditChainService()

    def _estimate_tokens(self, text: str, tokenizer_fn: Optional[Callable[[str], int]] = None) -> int:
        """Estimate token consumption using custom callback or conservative 2.8 chars/token ceiling."""
        if not text:
            return 0
        if tokenizer_fn is not None:
            try:
                return int(tokenizer_fn(text))
            except Exception:
                pass
        return int(len(text) / 2.8) + 1

    def _sanitize_and_check_injection(
        self,
        title: str,
        body: str,
        enable_injection_defense: bool,
    ) -> tuple[str, str, Optional[str]]:
        """
        Execute 3-Stage NFKC/XML/Heuristic sanitization.
        
        Returns tuple `(escaped_title, escaped_body, matched_breakout_pattern)`.
        If `matched_breakout_pattern` is not None, the item contains active breakout/override injection.
        """
        if not enable_injection_defense:
            return html.escape(title), html.escape(body), None

        # Stage 1: Canonicalize via NFKC and strip zero-width characters
        norm_title = unicodedata.normalize("NFKC", title)
        norm_body = unicodedata.normalize("NFKC", body)

        zero_width_regex = re.compile(r"[\u200b\u200c\u200d\ufeff\x00-\x1f]+")
        clean_title = zero_width_regex.sub("", norm_title)
        clean_body = zero_width_regex.sub("", norm_body)

        combined = f"{clean_title}\n{clean_body}"

        # Stage 2: Active threat breakout interception
        matched_pattern: Optional[str] = None
        for pattern in self.BREAKOUT_PATTERNS:
            match = pattern.search(combined)
            if match:
                matched_pattern = match.group(0)
                break

        # Stage 3: Structural XML escaping (`&lt;|im_start|&gt;` renders instruction delimiters inert)
        escaped_title = html.escape(clean_title, quote=True)
        escaped_body = html.escape(clean_body, quote=True)

        return escaped_title, escaped_body, matched_pattern

    async def assemble_context(
        self,
        session: Union[Any, Any],
        caller: CallerContext,
        query_text: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        explicit_item_ids: Optional[List[Union[str, uuid.UUID]]] = None,
        max_tokens: int = 4096,
        similarity_threshold: float = 0.7,
        domain_namespaces: Optional[List[str]] = None,
        enable_injection_defense: bool = True,
        strict_security_abort: bool = False,
        tokenizer_fn: Optional[Callable[[str], int]] = None,
    ) -> Dict[str, Any]:
        """Execute clearance-scoped retrieval and assemble a sanitized, lineage-tracked LLM context block."""
        # Precondition Step 0: Transaction Boundary Assertion (`Section 15`)
        if hasattr(session, "in_transaction") and callable(session.in_transaction):
            if not session.in_transaction():
                raise ContextAssemblyError(
                    "Database session must be inside an active transaction boundary (`Section 15 Precondition Step 0`)"
                )

        # Sanitize token ceiling vs mandatory system reserve
        max_tokens = max(1, int(max_tokens))
        if max_tokens <= self.SYSTEM_FRAME_RESERVE:
            raise TokenBudgetExhaustionError(max_tokens=max_tokens, required_reserve=self.SYSTEM_FRAME_RESERVE)

        candidate_items: List[Dict[str, Any]] = []
        seen_item_ids: set = set()
        items_omitted_clearance = 0

        # Channel 1: Explicit known citations (`e.g., regulatory or legal documents`)
        if explicit_item_ids:
            for raw_id in explicit_item_ids:
                try:
                    target_id = str(raw_id)
                    if target_id in seen_item_ids:
                        continue
                    item_dto = await self.retrieval_service.get_item_by_id(session, caller, target_id)
                    candidate_items.append(item_dto)
                    seen_item_ids.add(target_id)
                except (ItemNotFoundError, SearchClearanceViolationError):
                    items_omitted_clearance += 1
                except Exception:
                    items_omitted_clearance += 1

        # Channel 2: Semantic & Lexical search hits
        if query_text or query_vector:
            search_hits = await self.retrieval_service.search(
                session=session,
                caller=caller,
                query_text=query_text,
                query_vector=query_vector,
                limit=50,
                offset=0,
                similarity_threshold=similarity_threshold,
                domain_namespaces=domain_namespaces,
            )
            for hit in search_hits:
                hit_id = str(hit.get("item_id", ""))
                if hit_id and hit_id not in seen_item_ids:
                    candidate_items.append(hit)
                    seen_item_ids.add(hit_id)

        # Process candidates through Atomic Token Budgeting & 3-Stage Sanitization
        current_tokens = self.SYSTEM_FRAME_RESERVE
        assembled_chunks: List[str] = []
        lineage_manifest: List[Dict[str, Any]] = []
        items_rejected_injection = 0
        items_omitted_budget = 0

        for item in candidate_items:
            # Verify mandatory lineage attributes
            item_id = str(item.get("item_id", ""))
            if not item_id:
                raise LineageIntegrityError(missing_field="item_id")
            version = item.get("version")
            if version is None:
                raise LineageIntegrityError(missing_field="version", item_id=item_id)
            namespace = str(item.get("domain_namespace", ""))
            if not namespace:
                raise LineageIntegrityError(missing_field="domain_namespace", item_id=item_id)

            title = str(item.get("title", ""))
            body = str(item.get("body", ""))
            score = float(item.get("score", 0.0))
            sensitivity = str(item.get("sensitivity_label", "INTERNAL"))

            # Run 3-Stage Prompt Injection Defense
            escaped_title, escaped_body, matched_breakout = self._sanitize_and_check_injection(
                title=title,
                body=body,
                enable_injection_defense=enable_injection_defense,
            )

            if matched_breakout is not None:
                if strict_security_abort:
                    raise PromptInjectionSecurityError(item_id=item_id, pattern_matched=matched_breakout)
                items_rejected_injection += 1
                continue

            # Construct structural XML citation block
            chunk_xml = (
                f'<knowledge_citation id="{item_id}" namespace="{namespace}" version="{version}" score="{score:.4f}">\n'
                f'<title>{escaped_title}</title>\n'
                f'<body>{escaped_body}</body>\n'
                f'</knowledge_citation>'
            )

            chunk_tokens = self._estimate_tokens(chunk_xml, tokenizer_fn) + self.CITATION_OVERHEAD_PER_ITEM

            # Atomic Budget Packing (`never half-truncating`)
            if current_tokens + chunk_tokens > max_tokens:
                items_omitted_budget += 1
                continue

            # Pack chunk and record lineage manifest entry
            current_tokens += chunk_tokens
            assembled_chunks.append(chunk_xml)

            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            lineage_manifest.append(
                {
                    "item_id": item_id,
                    "version": int(version),
                    "domain_namespace": namespace,
                    "sensitivity_label": sensitivity,
                    "score": score,
                    "content_hash": content_hash,
                }
            )

        assembled_prompt = "\n\n".join(assembled_chunks) if assembled_chunks else ""

        # Traceable 2-Hop Cryptographic Audit Chaining (`RSK-04`)
        # Log STAGE_6_CONTEXT_ASSEMBLY without storing restricted raw body/text keys inside details
        target_uuid: Optional[uuid.UUID] = None
        if lineage_manifest:
            try:
                target_uuid = uuid.UUID(lineage_manifest[0]["item_id"])
            except (ValueError, TypeError):
                target_uuid = None

        audit_payload = AuditEventPayload(
            action_type=AuditActionEnum.RETRIEVE_SUCCESS,
            actor_id=caller.user_id,
            target_id=target_uuid,
            details={
                "stage": "STAGE_6_CONTEXT_ASSEMBLY",
                "operation": "assemble_context",
                "max_tokens": max_tokens,
                "similarity_threshold": float(similarity_threshold),
                "namespaces_queried": domain_namespaces or list(caller.allowed_namespaces),
                "candidates_retrieved": len(candidate_items),
                "items_included": len(lineage_manifest),
                "items_rejected_injection": items_rejected_injection,
                "items_omitted_budget": items_omitted_budget,
                "items_omitted_clearance": items_omitted_clearance,
                "tokens_used": current_tokens,
                "included_manifest_hashes": [m["content_hash"] for m in lineage_manifest],
            },
        )
        await self.audit_service.log_event(session=session, payload=audit_payload)

        return {
            "assembled_prompt": assembled_prompt,
            "lineage_manifest": lineage_manifest,
            "tokens_used": current_tokens,
            "items_included": len(lineage_manifest),
            "items_rejected_injection": items_rejected_injection,
            "items_omitted_budget": items_omitted_budget,
            "items_omitted_clearance": items_omitted_clearance,
        }
