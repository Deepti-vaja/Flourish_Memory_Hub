"""
Flourish Governed Memory Hub - Immutable Security Caller Context (`Section 26.1`)
Defines the frozen CallerContext dataclass and SecurityResolverProtocol contract
to ensure that downstream domain services never process raw HTTP headers or loose dictionaries.
"""

from dataclasses import dataclass
from typing import Dict, Protocol, Set, runtime_checkable
from uuid import UUID

from app.audit.exceptions import InvalidCallerContextError


@dataclass(frozen=True)
class CallerContext:
    """
    Immutable representation of an authenticated identity (AI Agent, Domain Steward, or Engineer).
    Constructed exclusively by SecurityContextResolver during ASGI middleware interception.
    Enforces strict typing and immutability (`FrozenInstanceError` if mutated post-creation).
    """
    user_id: UUID
    identity_key: str
    functional_role: str               # 'ENGINEER', 'STEWARD', 'ADMIN', 'AGENT'
    allowed_namespaces: Set[str]       # Horizontal clearances: e.g. {'eng.core', 'eng.infra'}
    max_sensitivity_level: int         # Vertical clearance: 1 (PUBLIC) to 4 (RESTRICTED)
    correlation_id: str                # X-Request-ID for distributed tracing and correlation


@runtime_checkable
class SecurityResolverProtocol(Protocol):
    """
    Contract for resolving HTTP request headers or tokens into an authenticated CallerContext.
    Downstream ASGI middleware (Stage 7) must implement this protocol cleanly.
    """
    async def resolve_context(self, headers: Dict[str, str]) -> CallerContext:
        """
        Resolves raw request headers into an immutable CallerContext.
        Raises `InvalidCallerContextError` if required headers/claims are missing or malformed.
        """
        ...


__all__ = [
    "CallerContext",
    "SecurityResolverProtocol",
    "InvalidCallerContextError",
]
