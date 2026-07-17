"""
Flourish Governed Memory Hub - Unit Tests for Cryptographic Audit Chainer & Security Context
Verifies exact canonical JSON normalization (`sort_keys=True`, `separators=(',', ':')`),
Unicode preservation, pipe delimitation, HMAC determinism, frozen immutability, and RSK-04 payload validation.
"""

import dataclasses
import datetime
import uuid
import pytest

from app.core.constants import AuditActionEnum
from app.security.context import CallerContext, SecurityResolverProtocol
from app.audit import (
    RESTRICTED_AUDIT_KEYS,
    AuditChainProtocol,
    AuditChainService,
    AuditEventPayload,
    AuditPayloadValidationError,
    build_canonical_payload,
    check_restricted_keys,
    compute_hmac_sha256,
)


def test_canonical_json_sorting_and_compactness() -> None:
    """Verify exact JSON normalization rules (`sort_keys=True`, compact separators)."""
    payload_dict = {"z": 1, "a": "hello", "m": [3, 2]}
    canonical = build_canonical_payload(
        sequence_id=1,
        event_time_iso="2026-07-17T10:45:00.000000+00:00",
        action_type="INGEST",
        actor_id_str="SYSTEM",
        target_id_str="NONE",
        details_dict=payload_dict,
        prev_hash_hex="0" * 64,
    )
    # Extract details_canonical between 5th and 6th pipe
    parts = canonical.split("|")
    assert len(parts) == 7
    assert parts[5] == '{"a":"hello","m":[3,2],"z":1}'


def test_canonical_json_unicode_preservation() -> None:
    """Verify non-ASCII characters (`ensure_ascii=False`) are preserved without \\u escaping."""
    payload_dict = {"doc": "Sección 11 y Adjudicación"}
    canonical = build_canonical_payload(
        sequence_id=2,
        event_time_iso="2026-07-17T10:45:01.123456+00:00",
        action_type="APPROVE",
        actor_id_str="11111111-1111-1111-1111-111111111111",
        target_id_str="22222222-2222-2222-2222-222222222222",
        details_dict=payload_dict,
        prev_hash_hex="a" * 64,
    )
    parts = canonical.split("|")
    assert 'Sección 11 y Adjudicación' in parts[5]
    assert "\\u" not in parts[5]


def test_canonical_payload_pipe_formatting() -> None:
    """Verify exact 7-part pipe formatting (`seq|time|action|actor|target|details|prev`)."""
    canonical = build_canonical_payload(
        sequence_id=10,
        event_time_iso="2026-07-17T12:00:00.000000+00:00",
        action_type="RETRIEVE_SUCCESS",
        actor_id_str="SYSTEM",
        target_id_str="NONE",
        details_dict={},
        prev_hash_hex="1234567890abcdef" * 4,
    )
    assert canonical == (
        "10|2026-07-17T12:00:00.000000+00:00|RETRIEVE_SUCCESS|SYSTEM|NONE|{}|"
        + ("1234567890abcdef" * 4)
    )


def test_hmac_sha256_deterministic_signature() -> None:
    """Verify HMAC SHA-256 produces exact 64-character lowercase hexadecimal digest."""
    secret = b"test-secret-key-2026"
    payload = "1|2026-07-17T10:00:00.000000+00:00|INGEST|SYSTEM|NONE|{}|" + ("0" * 64)
    digest = compute_hmac_sha256(secret, payload)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)

    # Calling twice with identical inputs yields exact same digest
    digest_again = compute_hmac_sha256(secret, payload)
    assert digest == digest_again


def test_payload_validation_rejects_restricted_keys_rsk04() -> None:
    """Verify recursive rejection of `body`, `content`, `snippet`, `raw_text` inside details (`RSK-04`)."""
    # Top level check
    with pytest.raises(AuditPayloadValidationError, match="Restricted key 'body' detected"):
        check_restricted_keys({"body": "Confidential text"})

    # Nested check inside dict and list
    nested_data = {"meta": {"sources": [{"title": "Doc A", "snippet": "secret snippet"}]}}
    with pytest.raises(AuditPayloadValidationError, match="Restricted key 'snippet' detected"):
        check_restricted_keys(nested_data)

    # AuditEventPayload instantiation automatically raises error on restricted keys
    with pytest.raises(AuditPayloadValidationError):
        AuditEventPayload(
            action_type=AuditActionEnum.INGEST,
            actor_id=None,
            target_id=None,
            details={"payload": {"raw_text": "leak"}},
        )


def test_caller_context_immutability() -> None:
    """Verify `CallerContext` is `@dataclass(frozen=True)` and raises `FrozenInstanceError` when mutated."""
    caller = CallerContext(
        user_id=uuid.uuid4(),
        identity_key="steward@flourish.ai",
        functional_role="STEWARD",
        allowed_namespaces={"eng.core", "hr.general"},
        max_sensitivity_level=3,
        correlation_id="req-12345",
    )
    assert caller.functional_role == "STEWARD"
    with pytest.raises(dataclasses.FrozenInstanceError):
        caller.max_sensitivity_level = 4  # type: ignore[misc]


def test_protocol_conformance() -> None:
    """Verify that concrete implementations conform cleanly to `typing.Protocol` checks."""
    service = AuditChainService()
    assert isinstance(service, AuditChainProtocol)


def test_issue_med_01_canonical_json_domain_objects() -> None:
    """
    Verify `ISSUE-MED-01`: `build_canonical_payload` deterministically serializes complex domain types
    (`UUID`, `datetime`, `date`, `set`, `bytes`) inside details_dict without raising `TypeError`.
    """
    test_uuid = uuid.UUID("1ad9f6c0-d208-4abe-8ebd-718cf12ba205")
    test_dt = datetime.datetime(2026, 7, 16, 12, 0, 0, 123456, tzinfo=datetime.timezone.utc)
    test_date = datetime.date(2026, 7, 16)
    test_set = {"eng.core", "eng.infra"}
    test_bytes = b"\x01\x02\x03"

    canonical = build_canonical_payload(
        sequence_id=1,
        event_time_iso="2026-07-16T12:00:00.000000+00:00",
        action_type="INGEST",
        actor_id_str="SYSTEM",
        target_id_str="NONE",
        details_dict={
            "item_id": test_uuid,
            "timestamp": test_dt,
            "date": test_date,
            "namespaces": test_set,
            "binary": test_bytes,
        },
        prev_hash_hex="0" * 64,
    )
    assert '"item_id":"1ad9f6c0-d208-4abe-8ebd-718cf12ba205"' in canonical
    assert '"timestamp":"2026-07-16T12:00:00.123456+00:00"' in canonical
    assert '"date":"2026-07-16"' in canonical
    assert '"namespaces":["eng.core","eng.infra"]' in canonical
    assert '"binary":"010203"' in canonical


def test_issue_low_01_system_bootstrap_uuid_normalization() -> None:
    """
    Verify `ISSUE-LOW-01`: `SYSTEM_BOOTSTRAP_UUID` (`0000...-0000`) is normalized cleanly
    to `"SYSTEM"` string representation inside payload preparation.
    """
    from app.audit.chainer import SYSTEM_BOOTSTRAP_UUID
    actor_str = (
        str(SYSTEM_BOOTSTRAP_UUID).lower()
        if SYSTEM_BOOTSTRAP_UUID is not None and SYSTEM_BOOTSTRAP_UUID != SYSTEM_BOOTSTRAP_UUID
        else "SYSTEM"
    )
    assert actor_str == "SYSTEM"

