"""Tests for ModelRouter — local lock, cloud opt-in, defaults."""

from __future__ import annotations

from unittest.mock import patch


def _make_config(cloud_enabled: bool = False, cloud_agents: list | None = None):
    from nexus.config import ModelCloudConfig, ModelsConfig, NexusConfig

    config = NexusConfig()
    config.models = ModelsConfig(
        local_model="qwen3.5:9b",
        cloud_agents=ModelCloudConfig(
            enabled=cloud_enabled,
            model="qwen3.5:cloud",
            agents=cloud_agents or [],
        ),
    )
    return config


class TestModelRouter:
    def test_family_coordinator_always_local(self):
        """family_coordinator is locked to local regardless of config."""
        from nexus.llm.router import ModelRouter

        config = _make_config(cloud_enabled=True, cloud_agents=["family_coordinator"])
        with patch("nexus.llm.router.ChatOllama") as mock_ollama:
            mock_ollama.return_value = object()
            router = ModelRouter(config)
            model = router.get_model("family_coordinator")
            # Should be the local model (first ChatOllama call)
            assert model is router._local_model

    def test_cloud_enabled_returns_cloud_for_listed_agents(self):
        """Cloud agent gets cloud model when cloud is enabled and listed."""
        from nexus.llm.router import ModelRouter

        config = _make_config(cloud_enabled=True, cloud_agents=["orchestrator"])
        with patch("nexus.llm.router.ChatOllama") as mock_ollama:
            instances = [object(), object()]
            mock_ollama.side_effect = instances
            router = ModelRouter(config)
            model = router.get_model("orchestrator")
            assert model is router._cloud_model

    def test_cloud_disabled_returns_local_for_all(self):
        """When cloud is disabled, all agents get local model."""
        from nexus.llm.router import ModelRouter

        config = _make_config(cloud_enabled=False, cloud_agents=["orchestrator", "synthesizer"])
        with patch("nexus.llm.router.ChatOllama") as mock_ollama:
            mock_ollama.return_value = object()
            router = ModelRouter(config)
            assert router.get_model("orchestrator") is router._local_model
            assert router.get_model("synthesizer") is router._local_model

    def test_unknown_agent_returns_local(self):
        """Any agent not in cloud list gets local model."""
        from nexus.llm.router import ModelRouter

        config = _make_config(cloud_enabled=True, cloud_agents=["orchestrator"])
        with patch("nexus.llm.router.ChatOllama") as mock_ollama:
            mock_ollama.return_value = object()
            router = ModelRouter(config)
            assert router.get_model("meteorology") is router._local_model
            assert router.get_model("safety") is router._local_model
