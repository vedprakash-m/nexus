"""
FastAPI app factory — Tech §9.2.

Bound to 127.0.0.1 only (no network exposure).
Docs disabled (local tool, no external consumers).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nexus.config import NexusConfig
from nexus.web.routes import router as api_router

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialize tool registry and model router once at startup."""
    import nexus.runtime as runtime
    from nexus.llm.router import ModelRouter
    from nexus.tools.registry import build_registry

    config: NexusConfig = app.state.config
    runtime.tool_registry = build_registry(config)
    runtime.model_router = ModelRouter(config)

    # ISSUE-08: Periodic background eviction of stale _plan_contexts entries
    import asyncio as _asyncio
    from nexus.web.routes import _plan_contexts, _plan_context_timestamps

    async def _evict_stale_contexts() -> None:
        import time as _time

        while True:
            await _asyncio.sleep(1800)  # every 30 minutes
            _now = _time.monotonic()
            _stale = [k for k, t in list(_plan_context_timestamps.items()) if _now - t > 7200]
            for k in _stale:
                _plan_contexts.pop(k, None)
                _plan_context_timestamps.pop(k, None)

    _asyncio.create_task(_evict_stale_contexts())
    yield
    # Cleanup on shutdown (no-op for singletons)


def create_app(config: NexusConfig) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        config: Loaded NexusConfig (passed in from CLI launcher).

    Returns:
        Configured FastAPI app ready to be served by uvicorn.
    """
    app = FastAPI(
        title="Nexus",
        description="Local-first weekend planning assistant",
        version="0.1.0",
        docs_url=None,  # No Swagger — local tool
        redoc_url=None,  # No ReDoc
        lifespan=_lifespan,
    )

    # Attach config to app state for route handlers
    app.state.config = config

    # Static files (favicon, WebSocket client JS)
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # All routes (pages + API + WebSocket)
    app.include_router(api_router)

    return app
