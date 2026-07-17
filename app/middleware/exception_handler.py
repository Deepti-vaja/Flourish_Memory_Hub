"""
ASGI / FastAPI Exception Handler Middleware (`Stage 7 Engine / Section 14 & 26.7`).
Translates domain exceptions from Stages 1 through 6 into standardized `ErrorResponse` JSON bodies
and exact HTTP status codes without flattening or overriding specific subclasses (`Risk #4 Remediation`).
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.audit.exceptions import (
    FlourishGovernanceError,
    InvalidCallerContextError,
    AuditEngineError,
)
from app.services.exceptions import (
    IngestionError,
    NamespaceNotFoundError,
    NamespaceAccessDeniedError,
    SensitivityViolationError,
    EmbeddingDimensionError,
    IngestionPayloadError,
)
from app.services.governance_exceptions import (
    GovernanceError,
    DocumentNotFoundError,
    StewardAuthorizationError,
    FourEyesPrincipleViolationError,
    DocumentNotPendingError,
)
from app.services.retrieval_exceptions import (
    RetrievalError,
    SearchClearanceViolationError,
    InvalidVectorDimensionError,
    ItemNotFoundError,
)
from app.services.context_exceptions import (
    ContextAssemblyError,
    TokenBudgetExhaustionError,
    PromptInjectionSecurityError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Registers exception handlers onto the FastAPI application in strict order of specificity (`Risk #4 Remediation`).
    Guarantees exact HTTP status code mapping and standardized JSON bodies.
    """

    # 1. Stage 2 Audit & Security Context Exceptions (`401 Unauthorized`)
    @app.exception_handler(InvalidCallerContextError)
    async def invalid_caller_context_handler(request: Request, exc: InvalidCallerContextError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "error": "INVALID_CALLER_CONTEXT",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    # 2. Item / Document / Namespace Not Found (`404 Not Found`)
    @app.exception_handler(ItemNotFoundError)
    async def item_not_found_handler(request: Request, exc: ItemNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": getattr(exc, "error_code", "ITEM_NOT_FOUND"),
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(DocumentNotFoundError)
    async def document_not_found_handler(request: Request, exc: DocumentNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": "DOCUMENT_NOT_FOUND",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(NamespaceNotFoundError)
    async def namespace_not_found_handler(request: Request, exc: NamespaceNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": "NAMESPACE_NOT_FOUND",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    # 3. Clearance & Authorization Violations (`403 Forbidden`)
    @app.exception_handler(SearchClearanceViolationError)
    async def search_clearance_handler(request: Request, exc: SearchClearanceViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": getattr(exc, "error_code", "CLEARANCE_VIOLATION"),
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(StewardAuthorizationError)
    async def steward_auth_handler(request: Request, exc: StewardAuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": "STEWARD_AUTHORIZATION_ERROR",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(FourEyesPrincipleViolationError)
    async def four_eyes_handler(request: Request, exc: FourEyesPrincipleViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": "FOUR_EYES_PRINCIPLE_VIOLATION",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(NamespaceAccessDeniedError)
    async def namespace_access_handler(request: Request, exc: NamespaceAccessDeniedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": "NAMESPACE_ACCESS_DENIED",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(SensitivityViolationError)
    async def sensitivity_violation_handler(request: Request, exc: SensitivityViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": "SENSITIVITY_VIOLATION",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    # 4. Prompt Injection Security Interception (`422 Unprocessable Entity / Security Trap`)
    @app.exception_handler(PromptInjectionSecurityError)
    async def prompt_injection_handler(request: Request, exc: PromptInjectionSecurityError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": getattr(exc, "error_code", "PROMPT_INJECTION_SECURITY_ABORT"),
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(EmbeddingDimensionError)
    async def embedding_dimension_handler(request: Request, exc: EmbeddingDimensionError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "EMBEDDING_DIMENSION_ERROR",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    # 5. Token Ceiling & State Transition Violations (`400 Bad Request / 409 Conflict`)
    @app.exception_handler(TokenBudgetExhaustionError)
    async def token_budget_handler(request: Request, exc: TokenBudgetExhaustionError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": getattr(exc, "error_code", "TOKEN_BUDGET_EXHAUSTED"),
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(IngestionPayloadError)
    async def ingestion_payload_handler(request: Request, exc: IngestionPayloadError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": "INGESTION_PAYLOAD_ERROR",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(InvalidVectorDimensionError)
    async def invalid_dimension_handler(request: Request, exc: InvalidVectorDimensionError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": getattr(exc, "error_code", "INVALID_VECTOR_DIMENSION"),
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    @app.exception_handler(DocumentNotPendingError)
    async def document_not_pending_handler(request: Request, exc: DocumentNotPendingError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": "DOCUMENT_NOT_PENDING",
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )

    # 6. Base Domain Errors Catch-All (`500 Internal Error / Custom Code`)
    @app.exception_handler(FlourishGovernanceError)
    async def base_governance_handler(request: Request, exc: FlourishGovernanceError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": getattr(exc, "error_code", "GOVERNANCE_ERROR"),
                "message": str(exc),
                "details": {"path": request.url.path}
            }
        )


__all__ = ["register_exception_handlers"]
