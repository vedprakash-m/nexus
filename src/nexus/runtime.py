"""
Runtime singletons — Tech §9.2, task 9.2/9.3.

`tool_registry` and `model_router` are initialized during FastAPI's
lifespan startup handler in server.py and imported directly by agents.

Tests override via:
    monkeypatch.setattr("nexus.runtime.tool_registry", mock_tool_registry)
    monkeypatch.setattr("nexus.runtime.model_router", mock_model_router)

This pattern is simpler than LangGraph config injection and avoids
passing registry through the state dict on every node invocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.llm.router import ModelRouter
    from nexus.tools.registry import ToolRegistry

# Populated during FastAPI lifespan startup — see server.py
tool_registry: "ToolRegistry | None" = None
model_router: "ModelRouter | None" = None
