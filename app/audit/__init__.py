"""
Flourish Governed Memory Hub - Audit Package
Exports the cryptographic audit chainer classes, interfaces, normalization routines, and exception hierarchy.
"""

from app.audit.chainer import (
    RESTRICTED_AUDIT_KEYS,
    AuditChainProtocol,
    AuditChainService,
    AuditEventPayload,
    AuditVerifyResult,
    build_canonical_payload,
    check_restricted_keys,
    compute_hmac_sha256,
)
from app.audit.exceptions import (
    AuditConcurrencyError,
    AuditEngineError,
    AuditPayloadValidationError,
    AuditTamperError,
    FlourishGovernanceError,
    InvalidCallerContextError,
)

__all__ = [
    "RESTRICTED_AUDIT_KEYS",
    "AuditChainProtocol",
    "AuditChainService",
    "AuditEventPayload",
    "AuditVerifyResult",
    "build_canonical_payload",
    "check_restricted_keys",
    "compute_hmac_sha256",
    "FlourishGovernanceError",
    "InvalidCallerContextError",
    "AuditEngineError",
    "AuditConcurrencyError",
    "AuditTamperError",
    "AuditPayloadValidationError",
]
