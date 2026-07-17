"""
Unit Tests for Stage 7 API Routing, Security Context Resolver, and Exception Middleware (`Offline`).
Verifies exact header parsing and HTTP status code translation (`400, 401, 403, 404, 422, 500`).
"""
import uuid
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.audit.exceptions import InvalidCallerContextError
from app.main import app
from app.security.context import CallerContext
from app.security.context_resolver import SecurityContextResolver
from app.services.governance_exceptions import StewardAuthorizationError, DocumentNotFoundError
from app.services.retrieval_exceptions import SearchClearanceViolationError, ItemNotFoundError
from app.services.context_exceptions import PromptInjectionSecurityError, TokenBudgetExhaustionError


@pytest.mark.asyncio
async def test_security_context_resolver_valid_headers():
    resolver = SecurityContextResolver()
    user_id = uuid.uuid4()
    headers = {
        "X-User-ID": str(user_id),
        "X-Identity-Key": "steward@flourish.corp",
        "X-Functional-Role": "STEWARD",
        "X-Allowed-Namespaces": "eng.core, hr.secret, fin.audit",
        "X-Sensitivity-Ceiling": "3",
        "X-Request-ID": "req-999-abc"
    }
    context = await resolver.resolve_context(headers)
    assert context.user_id == user_id
    assert context.identity_key == "steward@flourish.corp"
    assert context.functional_role == "STEWARD"
    assert context.allowed_namespaces == {"eng.core", "hr.secret", "fin.audit"}
    assert context.max_sensitivity_level == 3
    assert context.correlation_id == "req-999-abc"


@pytest.mark.asyncio
async def test_security_context_resolver_missing_user_id():
    resolver = SecurityContextResolver()
    with pytest.raises(InvalidCallerContextError) as exc_info:
        await resolver.resolve_context({})
    assert "Missing mandatory 'X-User-ID'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_security_context_resolver_malformed_user_id():
    resolver = SecurityContextResolver()
    with pytest.raises(InvalidCallerContextError) as exc_info:
        await resolver.resolve_context({"X-User-ID": "not-a-uuid"})
    assert "not a valid UUID" in str(exc_info.value)


@pytest.mark.asyncio
async def test_security_context_resolver_clamping_and_defaults():
    resolver = SecurityContextResolver()
    user_id = uuid.uuid4()
    headers = {
        "X-User-ID": str(user_id),
        "X-Allowed-Namespaces": "   ,  ",  # empty strings post split
        "X-Sensitivity-Ceiling": "99"      # out of bounds
    }
    context = await resolver.resolve_context(headers)
    assert context.allowed_namespaces == {"eng.core"}  # fallback
    assert context.max_sensitivity_level == 4          # clamped to max 4
    assert len(context.correlation_id) > 0             # auto-generated


def test_exception_handler_middleware_mapping():
    """
    Test offline status code translation using a scratch route with exact exception raising.
    """
    test_app = FastAPI()
    from app.middleware.exception_handler import register_exception_handlers
    register_exception_handlers(test_app)

    @test_app.get("/trigger/401")
    async def trigger_401():
        raise InvalidCallerContextError("Simulated 401 identity error")

    @test_app.get("/trigger/404")
    async def trigger_404():
        raise ItemNotFoundError(item_id="12345678-1234-5678-1234-567812345678")

    @test_app.get("/trigger/403")
    async def trigger_403():
        raise SearchClearanceViolationError("Simulated 403 clearance violation")

    @test_app.get("/trigger/422")
    async def trigger_422():
        raise PromptInjectionSecurityError(item_id="12345678-1234-5678-1234-567812345678", pattern_matched="ignore previous instructions")

    @test_app.get("/trigger/400")
    async def trigger_400():
        raise TokenBudgetExhaustionError(max_tokens=50, required_reserve=256)

    client = TestClient(test_app)

    res_401 = client.get("/trigger/401")
    assert res_401.status_code == 401
    assert res_401.json()["error"] == "INVALID_CALLER_CONTEXT"

    res_404 = client.get("/trigger/404")
    assert res_404.status_code == 404
    assert res_404.json()["error"] == "ITEM_NOT_FOUND"

    res_403 = client.get("/trigger/403")
    assert res_403.status_code == 403
    assert res_403.json()["error"] == "SEARCH_CLEARANCE_VIOLATION"

    res_422 = client.get("/trigger/422")
    assert res_422.status_code == 422
    assert res_422.json()["error"] == "PROMPT_INJECTION_SECURITY_ABORT"

    res_400 = client.get("/trigger/400")
    assert res_400.status_code == 400
    assert res_400.json()["error"] == "TOKEN_BUDGET_EXHAUSTED"
