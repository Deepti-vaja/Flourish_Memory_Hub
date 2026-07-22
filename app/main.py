"""
Flourish Governed Memory Hub — Stage 7 ASGI / FastAPI Application Entry Point (`app.main`).
Initializes the FastAPI server, CORS middleware, exception handlers, and `/api/v1` router.
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.middleware.exception_handler import register_exception_handlers


def create_app() -> FastAPI:
    """
    Factory function to initialize and configure the Flourish Governed Memory Hub ASGI application.
    """
    app = FastAPI(
        title="Flourish Governed Memory Hub API",
        version="1.0.0",
        description="Clearance-scoped, zero-trust, forensically audited memory and context assembly platform (`Stages 1–7 Engine`).",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    # Configure CORS (`allowing local development and frontend/ dashboard running on port 8080 or 3000`)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register domain exception handlers (`Section 14 & 26.7 / Risk #4 Remediation`)
    register_exception_handlers(app)

    # Include aggregated Stage 7 API router
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["Operational"])
    async def health_check() -> dict[str, str]:
        return {
            "status": "HEALTHY",
            "service": "Flourish Governed Memory Hub",
            "stage": "STAGE_7_ACTIVE",
        }

    # Mount frontend UI dashboard onto root (`/`) so http://127.0.0.1:8000/ serves the client application directly
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(root_dir, "frontend")
    if os.path.exists(frontend_dir):
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


# Singleton ASGI application instance required by uvicorn e.g. `uvicorn app.main:app --reload`
app = create_app()

__all__ = ["create_app", "app"]
