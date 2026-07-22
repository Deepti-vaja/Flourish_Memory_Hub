"""
FastAPI / ASGI Dependency Engine (`Stage 7 Controllers / Section 15 & 26.2`).
Provides transactional database session injection (`asserting session.in_transaction() is True`)
and authenticated `CallerContext` header resolution.
"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import async_session_maker
from app.security.context import CallerContext
from app.security.context_resolver import SecurityContextResolver


async def get_db_transaction() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an active AsyncSession wrapped inside `session.begin()` (`Section 15 Fail-Closed SLA`).
    Guarantees `session.in_transaction() is True` before entering any Stage 7 endpoint controller.
    If an endpoint raises an exception, the transaction rolls back cleanly; otherwise it auto-commits upon exit (`Risk #1 Remediation`).
    """
    async with async_session_maker() as session:
        try:
            async with session.begin():
                yield session
        except SQLAlchemyError as exc:
            # Traps ORM/SQLAlchemy transaction exceptions during generator unwinding
            raise exc
        finally:
            await session.close()


async def get_caller_context(request: Request) -> CallerContext:
    """
    Resolves raw HTTP request headers into an immutable `CallerContext` (`Section 26.1`).
    Raises `InvalidCallerContextError` if mandatory headers (e.g., `X-User-ID`) are missing or malformed.
    """
    resolver = SecurityContextResolver()
    headers_dict = {k: str(v) for k, v in request.headers.items()}
    return await resolver.resolve_context(headers_dict)


__all__ = ["get_db_transaction", "get_caller_context"]
