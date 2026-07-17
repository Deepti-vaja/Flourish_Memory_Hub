"""
Domain Exception Hierarchy for Component #6 (`Context Assembly & Lineage Engine — Stage 6 Engine`).

All exceptions inherit from `FlourishGovernanceError` (`Component #2 Base Exception`),
ensuring uniform trapping, mapping, and HTTP status code translation by Stage 7 routers (`Section 14`).
"""
from typing import Optional
from app.services.exceptions import FlourishGovernanceError


class ContextAssemblyError(FlourishGovernanceError):
    """Base exception for all Stage 6 Context Assembly engine failures (500 Internal Server Error)."""

    def __init__(self, message: str = "Context assembly operation failed"):
        super().__init__(message)
        self.error_code = "CONTEXT_ASSEMBLY_ERROR"
        self.message = message


class TokenBudgetExhaustionError(ContextAssemblyError):
    """
    Raised when requested max_tokens ceiling is smaller than mandatory system/citation overhead reserves (400 Bad Request).
    """

    def __init__(self, max_tokens: int, required_reserve: int):
        message = (
            f"Requested max_tokens ({max_tokens}) is less than mandatory structural reserve ({required_reserve} tokens). "
            "Cannot assemble even minimal prompt framing."
        )
        super().__init__(message)
        self.error_code = "TOKEN_BUDGET_EXHAUSTED"
        self.max_tokens = max_tokens
        self.required_reserve = required_reserve


class PromptInjectionSecurityError(ContextAssemblyError):
    """
    Raised when an active prompt injection or wrapper breakout sequence is detected AND strict_security_abort=True (422/403 Security Exception).
    """

    def __init__(self, item_id: str, pattern_matched: str):
        message = f"Adversarial prompt injection breakout detected in item '{item_id}' (matched pattern '{pattern_matched}') under strict abort mode"
        super().__init__(message)
        self.error_code = "PROMPT_INJECTION_SECURITY_ABORT"
        self.item_id = item_id
        self.pattern_matched = pattern_matched


class LineageIntegrityError(ContextAssemblyError):
    """
    Raised when a candidate document DTO returned by retrieval lacks required lineage markers (500 Internal Server Error).
    """

    def __init__(self, missing_field: str, item_id: Optional[str] = None):
        message = f"Candidate document DTO {f'(item_id={item_id}) ' if item_id else ''}missing mandatory lineage field: '{missing_field}'"
        super().__init__(message)
        self.error_code = "LINEAGE_INTEGRITY_ERROR"
        self.missing_field = missing_field
