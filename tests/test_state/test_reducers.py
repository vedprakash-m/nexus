"""Tests for state reducers — merge_verdicts, append_to_list, append_log."""

from __future__ import annotations

from nexus.state.schemas import AgentVerdict


def _make_verdict(agent: str, verdict: str = "APPROVED") -> AgentVerdict:
    return AgentVerdict(agent_name=agent, verdict=verdict, is_hard_constraint=False)


class TestMergeVerdicts:
    def test_append_new_agent(self):
        from nexus.state.reducers import merge_verdicts

        existing = [_make_verdict("meteorology")]
        new = [_make_verdict("logistics")]
        result = merge_verdicts(existing, new)
        assert len(result) == 2
        agents = {v.agent_name for v in result}
        assert agents == {"meteorology", "logistics"}

    def test_replaces_same_agent(self):
        from nexus.state.reducers import merge_verdicts

        existing = [_make_verdict("meteorology", "APPROVED")]
        new = [_make_verdict("meteorology", "REJECTED")]
        result = merge_verdicts(existing, new)
        assert len(result) == 1
        assert result[0].verdict == "REJECTED"

    def test_single_verdict_not_list(self):
        from nexus.state.reducers import merge_verdicts

        existing = [_make_verdict("meteorology")]
        result = merge_verdicts(existing, _make_verdict("logistics"))
        assert len(result) == 2

    def test_empty_existing(self):
        from nexus.state.reducers import merge_verdicts

        result = merge_verdicts([], [_make_verdict("meteorology")])
        assert len(result) == 1

    def test_idempotent_on_duplicate_input(self):
        """Applying the same verdict twice has no additional effect."""
        from nexus.state.reducers import merge_verdicts

        verdict = _make_verdict("meteorology", "APPROVED")
        result1 = merge_verdicts([], [verdict])
        result2 = merge_verdicts(result1, [verdict])
        assert len(result2) == 1
        assert result2[0].verdict == "APPROVED"

    def test_merge_four_parallel_agents(self):
        """Simulates all 4 review agents writing concurrently."""
        from nexus.state.reducers import merge_verdicts

        existing: list[AgentVerdict] = []
        agents = ["meteorology", "family_coordinator", "nutritional", "logistics"]
        for agent in agents:
            existing = merge_verdicts(existing, [_make_verdict(agent)])
        assert len(existing) == 4


class TestAppendLog:
    def test_timestamps_added(self):
        from nexus.state.reducers import append_log

        result = append_log([], ["Starting planning"])
        assert len(result) == 1
        assert "[" in result[0]  # timestamp bracket

    def test_single_string(self):
        from nexus.state.reducers import append_log

        result = append_log([], "single entry")
        assert len(result) == 1

    def test_appends_without_overwrite(self):
        from nexus.state.reducers import append_log

        existing = append_log([], "entry 1")
        result = append_log(existing, "entry 2")
        assert len(result) == 2


class TestAppendToList:
    def test_appends_list(self):
        from nexus.state.reducers import append_to_list

        result = append_to_list([1, 2], [3, 4])
        assert result == [1, 2, 3, 4]

    def test_appends_single_item(self):
        from nexus.state.reducers import append_to_list

        result = append_to_list([1, 2], 3)
        assert result == [1, 2, 3]
