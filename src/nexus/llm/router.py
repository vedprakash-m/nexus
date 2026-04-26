"""
ModelRouter — dispatches agents to the correct Ollama model.

Design: thin config lookup, not a complex routing engine.
Local→cloud switching is a model-name change (Ollama cloud tags),
so ChatOllama stays identical in both cases.

family_coordinator is HARD-LOCKED local — never add to cloud list.
"""

from __future__ import annotations

from langchain_ollama import ChatOllama

from nexus.config import NexusConfig


class ModelRouter:
    """
    Route agents to the appropriate Ollama model.

    Usage:
        router = ModelRouter(config)
        model = router.get_model("orchestrator")
        result = await model.with_structured_output(Schema).ainvoke(prompt)
    """

    # These agents ALWAYS use local model regardless of config.
    # Enforced in code — not overrideable by config.
    # FamilyCoordinator handles children's PII (PRD §10.1).
    LOCKED_LOCAL_AGENTS: frozenset[str] = frozenset({"family_coordinator"})

    def __init__(self, config: NexusConfig) -> None:
        self._config = config

        self._local_model = ChatOllama(
            model=config.models.local_model,
            base_url=config.ollama.base_url,
            temperature=0.2,  # low creativity for structured output
            reasoning=False,  # disable chain-of-thought (new Ollama engine; replaces /no_think)
            # No global format="json" — agents that need structured output use
            # with_structured_output() which sets format per-call. The synthesizer
            # needs prose output, so a global JSON lock would break narration.
        )

        self._cloud_model: ChatOllama | None = None
        if config.models.cloud_agents.enabled:
            self._cloud_model = ChatOllama(
                model=config.models.cloud_agents.model,
                base_url=config.ollama.base_url,
                temperature=0.4,  # slightly higher for narration quality
                reasoning=False,  # disable chain-of-thought
            )

    def get_model(self, agent_name: str) -> ChatOllama:
        """Return the appropriate model for a given agent."""
        # Hard lock: family coordinator never leaves local
        if agent_name in self.LOCKED_LOCAL_AGENTS:
            return self._local_model

        # Cloud opt-in: agent must be in config's cloud agents list
        if self._cloud_model is not None and agent_name in self._config.models.cloud_agents.agents:
            return self._cloud_model

        return self._local_model
