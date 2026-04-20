# Contributing to Nexus

## Dev Setup

**Requirements:** Python ≥ 3.14, [`uv`](https://docs.astral.sh/uv/), [`just`](https://github.com/casey/just)

```bash
git clone <repo>
cd nexus
uv sync           # install all dependencies from uv.lock
just run          # start the server and open browser
```

Run the full test suite:

```bash
just test         # all tests
just test-fast    # unit tests only (no LLM, no live APIs)
just test-agents  # agent tests
just test-graph   # graph routing + checkpoint tests
just test-tools   # tool provider tests
```

Lint and type-check:

```bash
just lint         # ruff check + ruff format
just typecheck    # pyright src/
```

---

## Project Structure

```
src/nexus/
├── agents/          # LangGraph node functions (one file per agent)
│   ├── base.py              # shared AgentContext helpers
│   ├── error_boundary.py    # @agent_error_boundary decorator
│   ├── meteorology.py       # weather review agent
│   ├── logistics.py         # driving-time + timeline agent
│   ├── nutritional.py       # meal-plan agent
│   ├── safety.py            # hard safety constraints
│   ├── family_coordinator.py
│   ├── orchestrator.py      # consensus check node
│   ├── objective.py         # parse_intent + draft_proposal
│   ├── synthesizer.py       # HTML/Markdown output generation
│   └── save_plan.py         # file persistence
├── graph/
│   ├── planner.py           # StateGraph definition + build_planning_graph()
│   └── runner.py            # run_planning() entry point (AsyncSqliteSaver)
├── state/
│   ├── graph_state.py       # WeekendPlanState TypedDict
│   ├── schemas.py           # AgentVerdict, FamilyMember, etc.
│   └── helpers.py           # all_agents_approved(), build_initial_state()
├── tools/
│   ├── interfaces.py        # Protocol definitions (WeatherTool, etc.)
│   ├── registry.py          # ToolRegistry — injected into graph state
│   └── providers/           # concrete implementations
│       ├── weather/         # open_meteo.py
│       ├── routing/
│       ├── activity/
│       └── places/
├── output/
│   ├── html.py              # Jinja2-backed render_plan_html()
│   └── renderer.py          # render_plan_markdown()
├── web/
│   ├── app.py               # FastAPI app factory
│   └── routes.py            # page + API routes
├── templates/               # Jinja2 .j2 templates
├── stats.py                 # plan stats (SQLite)
└── config.py                # NexusConfig (loaded from ~/.nexus/config.toml)
```

---

## Adding a New Tool Provider

Tool providers implement one of the `Protocol` interfaces in `src/nexus/tools/interfaces.py`.

**Example — add a new weather provider:**

1. Create `src/nexus/tools/providers/weather/my_provider.py`:

   ```python
   from nexus.tools.models import WeatherForecast, AirQuality, DaylightWindow
   from nexus.tools.interfaces import WeatherTool

   class MyWeatherProvider:
       """Implements WeatherTool protocol."""

       async def get_forecast(self, lat: float, lon: float, target_date: ...) -> WeatherForecast:
           ...

       async def get_air_quality(self, lat: float, lon: float) -> AirQuality:
           ...

       async def get_daylight_window(self, lat: float, lon: float, target_date: ...) -> DaylightWindow:
           ...
   ```

2. Wire it in `src/nexus/tools/registry.py` (or `config.py` if provider is config-driven).

3. Add tests in `tests/test_tools/test_my_provider.py` following the existing `pytest-httpx` pattern (mock HTTP calls via `httpx_mock`).

**Key rule:** The `WeekendPlanState["tool_registry"]` field holds a `ToolRegistry` instance. Agents never import providers directly — they receive the registry via state injection.

---

## Adding a New Agent

Agents are `async` functions that take `WeekendPlanState` and return a `dict` with state updates.

**Steps:**

1. Create `src/nexus/agents/my_agent.py`:

   ```python
   from __future__ import annotations
   from nexus.agents.error_boundary import agent_error_boundary
   from nexus.state.graph_state import WeekendPlanState
   from nexus.state.schemas import AgentVerdict, VerdictStatus

   @agent_error_boundary(agent_name="my_agent")
   async def my_agent(state: WeekendPlanState) -> dict:
       registry = state["tool_registry"]
       # ... agent logic ...
       verdict = AgentVerdict(
           agent="my_agent",
           status=VerdictStatus.APPROVED,
           rejection_reason=None,
           confidence=0.9,
       )
       return {"current_verdicts": [*state["current_verdicts"], verdict]}
   ```

2. Register the node in `src/nexus/graph/planner.py`:

   ```python
   from nexus.agents.my_agent import my_agent
   graph.add_node("my_agent", my_agent)
   ```

3. Add edges in `build_planning_graph()` and update `all_agents_approved()` in `src/nexus/state/helpers.py` if the agent participates in consensus.

4. Add tests in `tests/test_agents/test_my_agent.py`. Use the patterns from `tests/test_agents/test_logistics.py` or `test_meteorology.py`.

---

## Testing Conventions

- **Framework:** `pytest` with `asyncio_mode = "auto"` — all async tests run without `@pytest.mark.asyncio`.
- **Async mocks:** Always stub `.ainvoke` explicitly:
  ```python
  # Correct
  llm = MagicMock()
  llm.ainvoke = AsyncMock(return_value=mock_response)

  # Wrong — AsyncMock() itself is not callable as ainvoke
  llm = AsyncMock(return_value=mock_response)
  ```
- **State dict:** Use `_base_state()` from `tests/test_graph/test_routing.py` as the canonical minimal state fixture. Always use dict access (`state["key"]`), never dot notation.
- **HTTP mocking:** Use `pytest-httpx`'s `httpx_mock` fixture to intercept external API calls.
- **No live APIs in unit tests:** All LLM and HTTP calls must be mocked. Live calls belong in `tests/test_e2e/` and are skipped in CI.
- **Snapshot tests:** `tests/test_output/test_html_render.py` includes a snapshot regression test. If you change `plan.html.j2`, delete `tests/fixtures/plan_snapshot.html` and re-run to regenerate the baseline.

---

## Code Style

| Tool | Command | What it checks |
|------|---------|----------------|
| `ruff check` | `just lint` | PEP 8, import order, unused vars |
| `ruff format` | `just lint` | Formatting (Black-compatible) |
| `pyright` | `just typecheck` | Static types (`--strict` on `src/`) |

- `from __future__ import annotations` at the top of every module.
- TypedDict state is accessed by key only — no dataclasses or Pydantic in graph state.
- Use `WeekendPlanState` type hints for all agent function parameters.
- Agents that write verdicts must append to `current_verdicts`, not replace it.
