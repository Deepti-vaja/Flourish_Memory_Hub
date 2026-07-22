"""
Security Context Resolver Implementation (`Stage 7 ASGI Boundary / Section 26.1 / 26.2`).
Resolves raw HTTP request headers into an immutable `CallerContext` dataclass,
enforcing strict UUID parsing, clearance string normalization, and correlation ID auto-generation.
"""

import uuid
from uuid import UUID

from app.security.context import CallerContext, InvalidCallerContextError


class SecurityContextResolver:
    """
    Production implementation of `SecurityResolverProtocol`.
    Parses and verifies raw headers, raising `InvalidCallerContextError` on malformed/missing identity claims.
    """

    async def resolve_context(self, headers: dict[str, str]) -> CallerContext:
        """
        Resolves raw request headers into an immutable CallerContext (`Section 26.1`).
        Header Keys (case-insensitive via normalized dictionary lookup):
          - x-user-id: UUID v4 string (Mandatory)
          - x-identity-key: str e.g., email or API key (Optional, defaults to stringified user_id)
          - x-functional-role: str e.g., 'ENGINEER', 'STEWARD', 'ADMIN', 'AGENT' (Optional, defaults to 'ENGINEER')
          - x-allowed-namespaces: comma-separated string e.g., 'eng.core,eng.api' (Optional, defaults to {'eng.core'})
          - x-sensitivity-ceiling: int string 1..4 (Optional, defaults to 1 PUBLIC)
          - x-request-id: str correlation ID (Optional, auto-generated if missing)
        """
        # Normalize header keys to lowercase for case-insensitive lookup
        norm_headers = {k.lower(): v for k, v in headers.items()}

        raw_user_id = norm_headers.get("x-user-id")
        if not raw_user_id:
            raise InvalidCallerContextError("Missing mandatory 'X-User-ID' header in HTTP request.")

        # Strict UUID parsing (`Risk #2 Remediation`)
        try:
            user_id = UUID(raw_user_id.strip())
        except (ValueError, TypeError, AttributeError):
            raise InvalidCallerContextError(
                f"Malformed 'X-User-ID' header: '{raw_user_id}' is not a valid UUID v4."
            )

        identity_key = norm_headers.get("x-identity-key", str(user_id)).strip()
        if not identity_key:
            identity_key = str(user_id)

        functional_role = norm_headers.get("x-functional-role", "ENGINEER").strip().upper()
        if not functional_role:
            functional_role = "ENGINEER"

        # Normalized namespaces set (`Risk #2 Remediation`)
        raw_namespaces = norm_headers.get("x-allowed-namespaces", "eng.core")
        allowed_namespaces: set[str] = {
            ns.strip() for ns in raw_namespaces.split(",") if ns.strip()
        }
        if not allowed_namespaces:
            allowed_namespaces = {"eng.core"}

        # Clamped sensitivity ceiling (`Risk #2 Remediation`)
        raw_level = norm_headers.get("x-sensitivity-ceiling", "1")
        try:
            level_int = int(raw_level.strip())
            max_sensitivity_level = max(1, min(4, level_int))
        except (ValueError, TypeError):
            max_sensitivity_level = 1

        # Auto-generated correlation ID if absent (`Risk #2 Remediation`)
        correlation_id = norm_headers.get("x-request-id") or norm_headers.get("x-correlation-id")
        if not correlation_id or not correlation_id.strip():
            correlation_id = uuid.uuid4().hex
        else:
            correlation_id = correlation_id.strip()

        return CallerContext(
            user_id=user_id,
            identity_key=identity_key,
            functional_role=functional_role,
            allowed_namespaces=allowed_namespaces,
            max_sensitivity_level=max_sensitivity_level,
            correlation_id=correlation_id,
        )


__all__ = ["SecurityContextResolver"]
