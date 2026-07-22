"""
Flourish Governed Memory Hub - Governance & Audit Exception Hierarchy
Defines the strict exception hierarchy for Component #2 (Cryptographic Audit Engine
and Immutable Caller Context resolution).
"""


class FlourishGovernanceError(Exception):
    """Base exception class for all Flourish Memory Hub governance and audit errors."""

    pass


class InvalidCallerContextError(FlourishGovernanceError):
    """
    Raised when HTTP request headers, tokens, or claims cannot be resolved
    into a valid, authenticated CallerContext (e.g., missing X-User-ID or clearance).
    """

    pass


class AuditEngineError(FlourishGovernanceError):
    """Base exception class for cryptographic audit ledger errors."""

    pass


class AuditConcurrencyError(AuditEngineError):
    """
    Raised when lock acquisition (SELECT ... FOR UPDATE) on audit_sequence_head
    times out or encounters a serialization deadlock under concurrency (RSK-01).
    """

    pass


class AuditTamperError(AuditEngineError):
    """
    Raised when state drift, broken hash chaining, or unauthorized post-facto row
    mutation is detected during write operations or verify_integrity diagnostic scans.
    """

    pass


class AuditPayloadValidationError(AuditEngineError):
    """
    Raised when an AuditEventPayload contains malformed structures or violates RSK-04
    by attempting to store restricted document content (body, snippets, or raw text)
    inside the audit ledger details dictionary.
    """

    pass
