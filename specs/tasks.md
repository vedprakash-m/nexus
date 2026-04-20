# Implementation Plan: Project Nexus

> **Version:** 1.3.0
> **Created:** 2026-04-18
> **Updated:** 2026-04-19 (Phase 11 UX Redesign completed; 204/204 tests passing)
> **Source Specs:** [nexus-prd.md](nexus-prd.md) · [nexus-tech-spec.md](nexus-tech-spec.md) · [nexus-ux-spec.md](nexus-ux-spec.md)
> **Spec Version:** 1.7.0 (all three documents)
> **Implementation Status:** ✅ COMPLETE — all phases 0–11 implemented and verified

---

## How to Read This Plan

Each phase builds on the previous one and ends with a concrete validation checkpoint. Tasks within a phase are ordered by dependency — do them top-to-bottom. Each task references the spec section it implements so you can look up the full contract.

**Notation:**
- `[Tech §X.Y]` — Technical Specification section
- `[PRD §X.Y]` — Product Requirements Document section
- `[UX §X.Y]` — UX Specification section
- **Bold tasks** are critical path — the phase cannot pass validation without them

---

## Phase 0 — Project Scaffolding

**Goal:** A buildable, lintable, testable Python project with all directories in place. No runtime logic yet.

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 0.1 | **Initialize project with `uv init`** | [Tech §15.4] | Create `pyproject.toml` with all dependencies listed in Tech Spec §2.1. Set `requires-python = ">=3.12"`. Register `nexus` script entry point → `nexus.cli.app:app`. Include `[project.optional-dependencies] dev` group. Configure `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` (required for `pytest-asyncio` — without this, all async tests fail with a collection error). **Package name correction:** Tech Spec §2.1 lists `python-markdown` but the correct PyPI package name is `Markdown` — use `uv add Markdown`; imported as `import markdown`. The name `python-markdown` on PyPI is a different, unrelated package. |
| 0.2 | **Create full directory structure** | [Tech §14] | Create every directory and empty `__init__.py` file listed in Tech Spec §14: `src/nexus/{cli,web,web/static,graph,llm,agents,state,tools,tools/providers,tools/providers/{weather,activity,places,routing},output,templates}`, `tests/{fixtures,test_state,test_agents,test_tools,test_graph,test_e2e,test_output}`, `docs/`, `specs/`. (`test_output/` is needed for task 7.16 HTML snapshot tests — omitting it from Phase 0 means the directory is missing when Phase 7 runs.) The `web/static/` directory is needed for the `StaticFiles` mount in the FastAPI server (favicon, WS client JS). |
| 0.3 | Create `__main__.py` | [Tech §14] | `src/nexus/__main__.py` → `from nexus.cli.app import app; app()` for `python -m nexus` support. |
| 0.4 | Create `justfile` | [Tech §15.2] | Implement all commands from Tech Spec §15.2: `run`, `plan`, `test`, `test-fast`, `test-agents`, `test-graph`, `test-tools`, `lint`, `format`, `typecheck`, `check`, `ollama-pull`, `ollama-status`. `test-tools` runs `uv run pytest tests/test_tools/ -v` and is the Phase 3 validation gate. |
| 0.5 | Create `.env.example` | [Tech §14] | Template: `YELP_API_KEY=`, `HIKING_PROJECT_KEY=` with comments. |
| 0.6 | Configure ruff + pyright | [Tech §2.1] | `ruff.toml` or `[tool.ruff]` in pyproject: target Python 3.12, line length 100, select rules. `pyrightconfig.json`: strict mode, `src/` as root. |
| 0.7 | Run `uv sync` and verify | — | `uv sync` succeeds. `uv run python -c "import langgraph; import fastapi; import pydantic"` passes. |
| 0.8 | Verify `just lint` and `just typecheck` pass | — | On the empty project, both return 0 exit code. |

**Validation:** `uv sync && just check` passes. `uv run nexus --help` prints Typer help (from stub in 0.3).

---

## Phase 1 — Configuration & State Foundation

**Goal:** Config loading, state schemas, and reducers — the data layer everything else builds on.

### 1A — Configuration System

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 1.1 | **Implement `NexusConfig` and all sub-models** | [Tech §10.3] | `src/nexus/config.py`: `ModelCloudConfig`, `ModelsConfig`, `OllamaConfig`, `ToolProvidersConfig`, `ToolsConfig`, `PlanningConfig`, `PathsConfig`, `NexusConfig`. Use `pydantic-settings`. `PathsConfig.model_post_init` derives subdirectories from `base_dir`. `NexusConfig.load()` reads `profile.yaml` using **`ruamel.yaml`** (not stdlib `yaml`) so that user-added comments are preserved on round-trip writes. `NexusConfig.save()` also uses `ruamel.yaml`. Import order note: `config.py` must NOT import from `state/` or `agents/`. |
| 1.2 | Implement `.env` parser | [Tech §10.3] | `_parse_env(path)` in `config.py`: read key-value pairs, strip quotes, skip comments. Simple — no need for python-dotenv dependency. |
| 1.3 | Create sample `profile.yaml` | [Tech §10.2] | Place in `tests/fixtures/sample_profile.yaml` with the full schema from Tech Spec §10.2. Also create a minimal version for tests. |
| 1.4 | **Test config loading** | — | `tests/test_config.py`: test loading from sample file, test default values, test `.env` merge, test missing file raises clear error, test `PathsConfig` derivation. |
| 1.5 | Create `~/.nexus/` directory bootstrap | [Tech §10.1] | Utility function `ensure_nexus_dirs(config: NexusConfig)` that creates all directories (`plans/`, `feedback/`, `cache/`, `checkpoints/`, `logs/`) with `mkdir(parents=True, exist_ok=True)`. Called during startup. |

### 1B — State Schemas & Reducers

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 1.6 | **Implement all Pydantic data models** | [Tech §6.1] | `src/nexus/state/schemas.py`: `UserProfile`, `FamilyMember`, `FamilyProfile`, `PlanRequirements`, `ActivityProposal`, `FamilyActivity`, `RestaurantRecommendation`, `AgentVerdict`, `FamilyPlanVerdict`, `NutritionalVerdict`. **`AgentVerdict` required fields:** `agent_name: str`, `verdict: Literal["APPROVED","REJECTED","NEEDS_INFO"]`, `is_hard_constraint: bool`, `confidence: float` (always `1.0` for deterministic agents; `0.0–1.0` for LLM agents — omitting this field causes `AttributeError` in the spec agent code which sets `confidence=1.0` on every verdict), `rejection_reason: str \| None = None`, `recommendation: str \| None = None`, `details: dict = {}`, `failure_type: AgentFailureType \| None = None`. **`ActivityProposal` required fields:** `activity_name: str`, `activity_type: str`, `location_coordinates: tuple[float, float]`, `endpoint_coordinates: tuple[float, float]`, `route_waypoints: list[tuple[float, float]]`, `start_time: datetime`, `estimated_duration_hours: float`, `estimated_return_after_sunset: bool`, `has_exposed_sections: bool`, `difficulty: str`, `max_distance_miles: float`, `min_elevation_ft: int = 0`, `search_radius_miles: float` (mutated: multiplied by 0.8 on logistics rejection), `require_cell_coverage: bool = False` (mutated: set to `True` on family no-cell rejection), `max_activity_hours: float` (mutated: reduced by 0.5 on logistics timeline conflict — this is what "compress time window by 30 min" means in the revision strategy). **Mutation note:** all revision adjustments use `state["plan_requirements"].model_copy(update={...})` to produce a modified copy — do NOT mutate the original in-place since the TypedDict reducer may replay it on loop-back. All agents read from this model — schema drift here causes `AttributeError` across agents 5.3–5.5. **`FamilyPlanVerdict`** (LLM structured output for family coordinator): fields `verdict: Literal["APPROVED","REJECTED","NEEDS_INFO"]`, `is_hard_constraint: bool`, `rejection_reason: str \| None`, `family_activities: list[FamilyActivity]`, plus `def to_agent_verdict(self) -> AgentVerdict`. **`NutritionalVerdict`** (LLM structured output for nutritional agent): fields `verdict`, `is_hard_constraint: bool`, `rejection_reason: str \| None`, `recommended_restaurant: RestaurantRecommendation \| None`, plus `def to_agent_verdict(self) -> AgentVerdict`. Both models are the `.with_structured_output()` targets for their respective LLM agents (Phase 5.10, 5.11) — omitting them will cause `AttributeError: 'dict' object has no attribute 'to_agent_verdict'` at runtime. |
| 1.7 | **Implement `DataConfidence` enum** | [Tech §6.6] | `src/nexus/state/confidence.py`: `DataConfidence(str, Enum)` with `VERIFIED`, `CACHED`, `ESTIMATED`. Document usage rules as docstring. |
| 1.8 | **Implement `AgentFailureType` enum and `HardConstraintDataUnavailable` exception** | [Tech §12.1, §12.3] | `src/nexus/resilience.py`: `AgentFailureType(str, Enum)` with `DATA_UNAVAILABLE`, `HARD_CONSTRAINT_BLOCK`, `TIMEOUT`, `INTERNAL_ERROR`. Also define `class HardConstraintDataUnavailable(Exception): pass` in the same file — this exception signals that a hard-constraint data source (e.g., weather, route) is unavailable with no cache fallback. It is raised by `fetch_with_fallback()` (task 3.5) and caught by `agent_error_boundary` (task 5.1). Must be importable as `from nexus.resilience import HardConstraintDataUnavailable`. |
| 1.9 | **Implement state reducers** | [Tech §6.3] | `src/nexus/state/reducers.py`: `merge_verdicts()` (replace-by-agent-name), `append_to_list()`, `append_log()` (timestamped). |
| 1.10 | **Implement `WeekendPlanState` TypedDict** | [Tech §6.2] | `src/nexus/state/graph_state.py`: Full TypedDict with all fields and `Annotated` reducers. Import models from `schemas.py`. Fields and types: `request_id: str`, `user_intent: str`, `target_date: date`, `user_profile: UserProfile`, `family_profile: FamilyProfile`, `plan_requirements: PlanRequirements | None`, `primary_activity: ActivityProposal | None`, `family_activities: list[FamilyActivity]`, `meal_plan: RestaurantRecommendation | None`, `proposal_history: Annotated[list[ActivityProposal], append_to_list]` (append reducer), `current_verdicts: Annotated[list[AgentVerdict], merge_verdicts]` (merge reducer), `weather_data: WeatherForecast | None`, `route_data: dict[str, RouteResult] | None` (keys: `"home_to_activity"`, `"activity_to_restaurant"`, `"restaurant_to_home"` — matches logistics agent return), `safety_data: dict | None` (**vestigial** — no agent in §5 writes this field; keep as `dict | None` for forward compatibility), `iteration_count: int`, `max_iterations: int`, `current_phase: Literal["drafting","reviewing","revising","validating","human_review","completed"]`, `rejection_context: str | None`, `pending_constraints: list[str]`, `negotiation_log: Annotated[list[str], append_log]` (append_log reducer), `human_feedback: str | None`, `output_html: str | None`, `output_markdown: str | None`, `backup_activity: ActivityProposal | None` (populated by synthesizer in task 5.12), `human_rejection_count: int`, `output_confidence_labels: dict[str, str] | None` (keys: data source names e.g. `"weather"`, `"route"`; values: display strings e.g. `"(est.)"`, `"(3hr cache)"`). |
| 1.11 | **Implement helper functions** | [Tech §6.4] | `src/nexus/state/helpers.py`: `build_initial_state()`, `all_agents_approved()`, `has_critical_safety_rejection()`, `get_verdict()`, `compute_tradeoff_summary()`, `prepare_llm_context()` (state slimming per §6.5 — prune `proposal_history` to last 2, `negotiation_log` to current iteration delta). |
| 1.12 | **Test reducers** | [Tech §13.2] | `tests/test_state/test_reducers.py`: `merge_verdicts` replaces same-agent verdicts, appends new agents, handles single and list input. `append_log` adds timestamps. Property: `merge_verdicts` is idempotent on duplicate input. |
| 1.13 | **Test schemas** | [Tech §13.2] | `tests/test_state/test_schemas.py`: All models validate with correct data, reject invalid data. `AgentVerdict` accepts all three verdict values. `FamilyPlanVerdict.to_agent_verdict()` returns a valid `AgentVerdict`. `NutritionalVerdict.to_agent_verdict()` returns a valid `AgentVerdict`. `build_initial_state()` produces valid state dict. |
| 1.14 | **Implement `AgentNode` Protocol** | [Tech §5.2] | `src/nexus/agents/base.py`: `class AgentNode(Protocol)` with `async def __call__(self, state: WeekendPlanState) -> dict`. This is the shared interface contract all 10 agent functions must satisfy. Used for type-checking in `pyright --strict` mode — any agent function with wrong signature is caught at typecheck time, not runtime. |  
| 1.15 | **Set up package `__init__.py` re-export pattern** | [Tech §14] | Document and stub the re-export pattern for `src/nexus/agents/__init__.py` and `src/nexus/state/__init__.py`. At Phase 1 these stay mostly empty; the comment in each `__init__.py` should say what will eventually be re-exported (e.g., `# Re-exports added in Phase 9 when agents are wired to graph`). This prevents silent import failures when task 9.1 wires real agents into the graph. |
| 1.16 | **Create `tests/conftest.py` with shared fixtures** | [Tech §13.2] | `tests/conftest.py`: `sample_config` fixture (loads `tests/fixtures/sample_profile.yaml`), `mock_llm` fixture (returns a mock `ChatOllama` that yields predictable structured output without Ollama running), `weather_clear` fixture (`WeatherForecast` with `precipitation_probability=5`, `aqi=42`, no lightning), `weather_rainy` fixture (`WeatherForecast` with `precipitation_probability=65`, triggers meteorology REJECTED), `mock_tool_registry` fixture (returns a duck-typed mock object satisfying `ToolRegistry.get()` — do NOT instantiate real `ToolRegistry` here since Phase 3 provider classes do not exist yet). Every test phase depends on these — creating them here ensures `just test-fast` works before any real provider exists. **Lazy import rule:** all imports inside fixture function bodies (never at module top-level) to prevent collection-time `ImportError` before later phases are implemented. Example: `def mock_tool_registry(): from nexus.tools.registry import ToolRegistry; ...`. Phase 1 tests never call Phase 3 fixtures, so deferred imports are never triggered until Phase 3 exists. |

**Validation:** `just test-fast` passes. All models serialize/deserialize correctly. Reducers merge correctly with synthetic data.

---

## Phase 2 — LLM Integration & Model Router

**Goal:** Ollama connection verified. Model router dispatches to correct model per agent.

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 2.1 | **Implement `ModelRouter`** | [Tech §3.3] | `src/nexus/llm/router.py`: `LOCKED_LOCAL_AGENTS = frozenset({"family_coordinator"})`. Constructor creates `_local_model` (ChatOllama with `temperature=0.2`, `format="json"`) and optional `_cloud_model`. `get_model(agent_name)` enforces local lock and cloud opt-in routing. |
| 2.2 | Create all prompt templates | [Tech §5.3–5.10] | `src/nexus/llm/prompts.py`: `INTENT_PARSE_PROMPT`, `ACTIVITY_RANKING_PROMPT`, `FAMILY_REVIEW_PROMPT`, `MENU_ANALYSIS_PROMPT`, `PLAN_NARRATION_PROMPT`. Each prompt template has `.format()` placeholders matching the agent code in Tech Spec §5. Include system instructions enforcing structured JSON output, user-facing language rules (no agent names, no scores — UX §1.3), and the revision strategy context (Tech §4.4). |
| 2.3 | Test model router | — | `tests/test_llm/test_router.py`: `family_coordinator` always returns local model. Cloud agent returns cloud model when enabled. Cloud disabled returns local for all. |

**Validation:** `ModelRouter` instantiates with sample config. `get_model("family_coordinator")` always returns local. Unit tests pass.

---

## Phase 3 — Tool Interface Layer

**Goal:** All external data source interfaces defined. MVP providers implemented with caching and graceful degradation.

### 3A — Interfaces & Infrastructure

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 3.1 | **Define tool data models** | [Tech §7.2] | `src/nexus/tools/models.py`: `Coordinates` (type alias for `tuple[float, float]`), `WeatherForecast`, `AirQuality`, `DaylightWindow`, `ActivityResult`, `RouteResult`, `PlaceResult`, `CoverageEstimate`. Each model includes `data_age_minutes: int` and a `confidence: DataConfidence` field. **Minimum required fields** (derived from agent code in §5 — missing any causes `AttributeError` at runtime): `WeatherForecast`: `precipitation_probability: float`, `lightning_risk: bool`, `conditions_text: str`, `temperature_high_f: float`. `AirQuality`: `aqi: int`. `DaylightWindow`: `sunrise: datetime`, `sunset: datetime`. `CoverageEstimate`: `has_likely_service: bool`, `road_proximity_miles: float`. `RouteResult`: `duration_minutes: float`, `distance_miles: float`. `ActivityResult`: `activity_id: str` (objective agent excludes already-proposed IDs by this key), `name: str`, `location_coordinates: tuple[float, float]`, `activity_type: str`, `difficulty: str`. |
| 3.2 | **Define Protocol interfaces** | [Tech §7.2] | `src/nexus/tools/interfaces.py`: `WeatherTool`, `ActivityTool`, `PlacesTool`, `RoutingTool` as `@runtime_checkable Protocol` classes. `RoutingTool` includes `nearest_road_distance()`. **Do NOT implement `estimate_cell_coverage()` here** — the concrete implementation is in task 3.12 (`coverage.py`). This file defines Protocol contracts only; add a comment `# estimate_cell_coverage() implemented in tools/providers/coverage.py` to document the relationship. |
| 3.3 | **Implement `ToolRegistry`** | [Tech §7.3] | `src/nexus/tools/registry.py`: `PROVIDERS` dict with explicit string-to-class mapping: `{"weather": OpenMeteoWeather, "activity": OverpassActivities, "places": YelpPlaces, "routing": OSRMRouting}`. These keys are what agents use in `tool_registry.get("weather")` and what `profile.yaml` references in provider config. Add `"activity_hiking": HikingProjectActivities` conditionally if config enables it. `ToolRegistry.__init__` instantiates each configured provider from this map. `get(tool_name)` returns the instance or raises `KeyError` with the list of available tool names in the error message. |
| 3.4 | **Implement `create_cache()`** | [Tech §11.1] | `src/nexus/cache.py`: `create_cache(cache_dir)` → `diskcache.Cache` with 500MB size limit. |
| 3.5 | **Implement `GracefulDegradation.fetch_with_fallback()`** | [Tech §12.1, PRD §6.5] | `src/nexus/resilience.py`: **`GracefulDegradation` is a class** (for namespacing), with `fetch_with_fallback` as an async static method. **Method signature:** `@staticmethod async def fetch_with_fallback(key: str, fetcher: Callable[[], Awaitable[T]], cache: Cache, is_hard_constraint: bool, default: T | None = None) -> tuple[T, DataConfidence]` where `T = TypeVar("T")`. `key`: cache lookup string (e.g., `"weather:37.7,-122.4:2026-04-19"`). `fetcher`: zero-arg async lambda wrapping the live API call (`lambda: tool.get_forecast(...)`). On every successful live fetch, write to both `key` (with TTL) and `stale:{key}` (`expire=None`). **API retry first** — 3 attempts with exponential backoff (0.5s, 1.0s, 2.0s + random jitter ±0.1s) per PRD §6.5 before falling back. **`diskcache` stale-read implementation note:** `diskcache.Cache.get()` enforces TTL by default and returns the default value on expired keys — you cannot read stale expired entries with a plain `get()`. Use a dual-key storage pattern: write every result twice — once under the normal key with the real TTL (e.g., `cache.set(key, value, expire=10800)`) and once under a `stale:{key}` prefix with `expire=None` (no expiry). The freshness fallback reads from `stale:{key}`, which always succeeds, and returns `DataConfidence.CACHED`. This pattern costs one extra write per cache set but requires no diskcache internals. Full waterfall: `try live (3 retries with backoff) → stale cache (read from `stale:` prefix, return DataConfidence.CACHED) → hard-domain raises `HardConstraintDataUnavailable` / soft-domain returns default with `DataConfidence.ESTIMATED``. Return `(result, DataConfidence)` tuple. Retry on `httpx.TimeoutException`, `httpx.ConnectError`, HTTP 429, and 5xx. Never retry on 401/403 (config error, not transient). |
| 3.6 | Test registry | — | `tests/test_tools/test_registry.py`: Registry resolves correct provider. Unknown tool raises `KeyError`. |

### 3B — MVP Providers

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 3.7 | **Implement `OpenMeteoWeather`** | [Tech §7.4] | `src/nexus/tools/providers/weather/open_meteo.py`: `get_forecast()`, `get_air_quality()`, `get_daylight_window()`. Use `httpx.AsyncClient` with 10s timeout. Cache with 3h TTL (weather) and 1h TTL (AQI). Parse Open-Meteo JSON response. Handle `httpx` errors for graceful degradation. |
| 3.8 | **Implement `OverpassActivities`** | [Tech §7.5] | `src/nexus/tools/providers/activity/overpass.py`: Query Overpass API for parks, beaches, bike routes, city POIs within radius. Return `list[ActivityResult]`. Cache static data 7 days, conditions 24h. |
| 3.9 | Implement `HikingProjectActivities` (optional) | [Tech §7.5] | `src/nexus/tools/providers/activity/hiking_project.py`: Trail search by coordinates, elevation, difficulty. Optional — Overpass covers all activity types. |
| 3.10 | **Implement `YelpPlaces`** | [Tech §7.5] | `src/nexus/tools/providers/places/yelp.py`: Restaurant and nearby-activity search. Menu data extraction. Requires `YELP_API_KEY`. Cache 7 days. |
| 3.11 | **Implement `OSRMRouting`** | [Tech §7.5] | `src/nexus/tools/providers/routing/osrm.py`: Public demo server (`router.project-osrm.org`). `get_route()` returns `RouteResult` with `duration_minutes`, `distance_miles`. `nearest_road_distance()` via Overpass. **Fallback strategy** per Tech §7.5: on 429/5xx/timeout → haversine × 1.4 Manhattan factor, 35/55 mph speed estimate, `DataConfidence.ESTIMATED`. |
| 3.12 | **Implement `estimate_cell_coverage()`** | [Tech §7.2] | `src/nexus/tools/providers/coverage.py`: Heuristic — `>2 mi from major road` or `>5 mi from town` → `has_likely_service = False`. Use cached Overpass road data. Always returns `DataConfidence.ESTIMATED`. Also implement `estimate_route_coverage()` for safety agent (percentage of route waypoints with poor coverage). |
| 3.13 | Test providers with recorded fixtures | [Tech §13.2] | `tests/test_tools/test_open_meteo.py`, `test_osrm.py`, `test_yelp.py`, `test_overpass.py`: Use `pytest-httpx` for HTTP mock injection (`httpx_mock` fixture intercepts all `httpx` calls within a test). **`pytest-httpx` does not record** — it is a pure mock library. Fixture JSON files (`tests/fixtures/{provider}_{endpoint}.json`) are created once by running a live curl or a one-time capture script, then committed to the repo. In each test: load the fixture file and inject via `httpx_mock.add_response(json=fixture_data)` before calling the provider function. Subsequent runs replay from in-memory mocks — no live API calls in CI. Do NOT use `vcrpy` — it does not integrate cleanly with `httpx` async clients. Test cache hits. Test error handling (timeout, 429, 5xx). Test OSRM fallback to haversine. Test `fetch_with_fallback` retry loop (use `httpx_mock.add_response(status_code=429)` twice then `httpx_mock.add_response(json=fixture_data)` → assert 3 total calls). |

**Validation:** Each provider returns correctly-typed results from recorded fixtures. Cache TTLs enforced. Graceful degradation returns `CACHED` or `ESTIMATED` on simulated failures. `just test-tools` passes.

---

## Phase 4 — LangGraph Core: Graph, Routing, Checkpointing

**Goal:** The planning graph compiles, routes correctly with synthetic state, and checkpoints to SQLite.

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 4.1 | **Implement `build_planning_graph()` with agent stubs** | [Tech §4.1] | `src/nexus/graph/planner.py`: **Phase 4 uses stub agent functions — define lightweight `async def` placeholders at the top of `planner.py` with correct signatures (`state: WeekendPlanState) -> dict`) but minimal bodies (just `return {}`). Task 9.1 replaces them with real implementations. This decouples graph compilation and routing tests from Phase 5.** Create `StateGraph(WeekendPlanState)`. Add all 10 nodes: `parse_intent`, `draft_proposal`, `review_meteorology`, `review_family`, `review_nutrition`, `review_logistics`, `check_consensus`, `review_safety`, `synthesize_plan`, `save_plan`. **Import note:** the Tech §4.1 spec import block lists 9 agents but omits `save_approved_plan` — add it manually: `from nexus.agents.save_plan import save_approved_plan`. Without this, `graph.add_node("save_plan", save_approved_plan)` raises `NameError` at graph construction time. Wire all edges per Tech §4.1: `START→parse_intent→draft_proposal`, conditional fan-out to 4 reviewers, all reviewers → `check_consensus`, conditional routing (`all_approved→review_safety`, `has_rejection→draft_proposal`, `max_iterations→review_safety`, `critical_failure→END`), `review_safety` conditional (`safe→synthesize_plan`, `unsafe→END`), `synthesize_plan→save_plan→END`. |
| 4.2 | **Implement routing functions** | [Tech §4.1] | `fan_out_to_reviewers()`: returns a list of **`Send` objects** — `[Send("review_meteorology", state), Send("review_family", state), Send("review_nutrition", state), Send("review_logistics", state)]`. Import `Send` from `langgraph.types`. **Critical:** returning bare node name strings will NOT produce true parallel execution in LangGraph — `Send` objects with the current state snapshot are required. `route_after_consensus()`: checks critical safety rejection, max iterations, all approved, NEEDS_INFO pass-through (REC-5), then `has_rejection`. `route_after_safety()`: safety verdict REJECTED → `unsafe`, else `safe`. |
| 4.3 | **Implement `run_planning()`** | [Tech §4.2] | `src/nexus/graph/runner.py`: Build graph, create `SqliteSaver` from config path, compile with `interrupt_after=["synthesize_plan"]`, build initial state via `build_initial_state()`, invoke with thread_id = request_id. |
| 4.4 | **Test graph routing with synthetic state** | [Tech §13.2] | `tests/test_graph/test_routing.py`: Inject known `WeekendPlanState` dicts with pre-set verdicts. Assert `route_after_consensus` returns correct string for: all approved, one REJECTED, max iterations hit, critical failure, all APPROVED+NEEDS_INFO. Assert `route_after_safety` routes correctly. |
| 4.5 | **Test consensus detection** | [Tech §13.2] | `tests/test_graph/test_consensus.py`: `all_agents_approved()` with complete/incomplete/rejected verdict sets. `has_critical_safety_rejection()` with typed failure types. |
| 4.6 | Test checkpoint persistence | [Tech §4.2] | Compile graph with SqliteSaver, invoke with a dummy state, verify checkpoint exists in SQLite, resume from checkpoint. |

**Validation:** Graph compiles without error. Routing tests pass with 100% coverage of all conditional branches. Checkpoint save/restore verified. `just test-graph` passes.

---

## Phase 5 — Agent Implementations

**Goal:** All agents produce correctly-typed output. Deterministic agents have exact-assertion tests. LLM agents have schema-validation tests.

### 5A — Error Boundary (prerequisite for all agents)

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 5.1 | **Implement `agent_error_boundary` decorator** | [Tech §12.4] | `src/nexus/agents/error_boundary.py`: Wrap agent functions. On `HardConstraintDataUnavailable` → re-raise. On `asyncio.TimeoutError` → `failure_type=TIMEOUT`. On other exceptions → `failure_type=INTERNAL_ERROR`. **Hard-constraint agents** → REJECTED verdict. **Soft-constraint agents** → NEEDS_INFO verdict. Never swallow exceptions silently. |
| 5.2 | Test error boundary | — | Test with mock agent that raises various exceptions. Verify hard-constraint returns REJECTED with correct failure_type. Verify soft-constraint returns NEEDS_INFO. Verify `HardConstraintDataUnavailable` propagates. |

### 5B — Deterministic Agents

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 5.3 | **Implement `meteorology_review()`** | [Tech §5.5] | `src/nexus/agents/meteorology.py`: Fetch forecast, AQI, daylight via tool registry. Threshold checks: `precipitation > 40` → REJECTED, `AQI > 100` → REJECTED, lightning + exposed sections → REJECTED, activity ends < 30 min before sunset → REJECTED. All state access via `state["field"]` dict syntax. Return `current_verdicts`, `weather_data`, `negotiation_log`. Wrap with `@agent_error_boundary("meteorology", is_hard_constraint=True)`. **`_suggest_alternative_window()` spec:** `def _suggest_alternative_window(forecast: WeatherForecast, daylight: DaylightWindow) -> str`. Returns a plain-English suggestion string placed in `AgentVerdict.recommendation` (never shown directly to the user — it feeds the revision strategy in task 5.9). Logic: if precipitation is the issue → `"Consider early morning start (before 9am) when precipitation probability is lower"`; if AQI is the issue → `"Consider a coastal or lower-elevation alternative route"`; if daylight is the issue → `"Start no later than {computed_latest_start}"`; if multiple → join with "; ". Returns `""` if no specific suggestion applies. |
| 5.4 | **Implement `logistics_review()`** | [Tech §5.8] | `src/nexus/agents/logistics.py`: Calculate routes (home→activity, activity→restaurant, restaurant→home) via routing tool. Sum driving minutes. Check against `state["family_profile"]["max_total_driving_minutes"]`. Detect timeline conflicts via `_detect_timeline_conflicts()`. **`_detect_timeline_conflicts()` spec:** `def _detect_timeline_conflicts(state: WeekendPlanState, home_to_activity: RouteResult, activity_to_restaurant: RouteResult | None, restaurant_to_home: RouteResult) -> list[str]`. Returns list of human-readable conflict strings (empty = no conflicts). Checks: (1) computed departure time (`activity.start_time - timedelta(minutes=home_to_activity.duration_minutes)`) before 6:00 AM → `"Departure before 6am"`; (2) total trip duration (`home_to_activity + activity + activity_to_restaurant + meal_time(60min) + restaurant_to_home`) > 12 hours → `"Full day exceeds 12 hours"`; (3) if `state["family_activities"]` contains any item with a fixed `start_time` that overlaps the primary activity window → `"Conflict with {member}'s {event}"`. All dict-access. Wrap with `@agent_error_boundary("logistics", is_hard_constraint=True)`. **Spec code caution:** Tech §5.8 code uses dot notation throughout (`state.family_profile`, `state.primary_activity`, `state.meal_plan`) — this is wrong for a TypedDict; use `state["family_profile"]`, `state["primary_activity"]`, `state["meal_plan"]` throughout. |
| 5.5 | **Implement `safety_review()`** | [Tech §5.9] | `src/nexus/agents/safety.py`: Final gate. Search hospitals within 30mi. Cross-check: remote + family + marginal weather → REJECTED. **Thresholds:** "remote" = no hospital found within 30 miles; "marginal weather" = `state["weather_data"].precipitation_probability > 30` (lower than meteorology's 40% hard threshold — safety applies a composite risk check); "family present" = `len(state["family_profile"].members) > 0` (always true for Nexus persona). Post-sunset return check is **independent from meteorology** (task 5.3 checks activity end; safety checks estimated return-home time = `activity.start_time + timedelta(hours=activity.estimated_duration_hours) + timedelta(minutes=restaurant_to_home.duration_minutes if meal_plan else home_to_activity.duration_minutes)` vs sunset). Route coverage heuristic: >50% poor coverage → REJECTED. Absolute veto power. Wrap with `@agent_error_boundary("safety", is_hard_constraint=True)`. **Spec code caution:** Tech §5.9 code uses dot notation (`state.primary_activity`, `state.weather_data`, `state.family_profile`) — this is wrong for a TypedDict; use `state["primary_activity"]`, `state["weather_data"]`, `state["family_profile"]` throughout. |
| 5.6 | **Test deterministic agents — exact assertions** | [Tech §13.2] | `tests/test_agents/test_meteorology.py`: Given `weather_clear` fixture → APPROVED. Given `weather_rainy` (65% precip) → REJECTED. Given AQI 115 → REJECTED. Given lightning + exposed → REJECTED. Given activity after sunset → REJECTED. Verify exact verdict values, not LLM text. Same pattern for logistics and safety. |

### 5C — LLM-Powered Agents

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 5.7 | **Implement `orchestrator_parse_intent()`** | [Tech §5.3] | `src/nexus/agents/orchestrator.py`: Get model via router. Use `.with_structured_output(PlanRequirements)`. Format `INTENT_PARSE_PROMPT` with intent, user profile, family profile. Return `plan_requirements`, `current_phase="drafting"`, `negotiation_log`. Wrap with `@agent_error_boundary("orchestrator", is_hard_constraint=False)`. |
| 5.8 | **Implement `orchestrator_check_consensus()`** | [Tech §5.3] | Same file. Deterministic — no LLM. Count verdicts, detect rejections, increment `iteration_count`. Return `iteration_count`, `current_phase`, `rejection_context`, `negotiation_log`. Inspect `pending_constraints` — if non-empty, drain queue into `rejection_context` and force `has_rejection` routing (mid-flight constraint queue per Tech §8.4). |
| 5.9 | **Implement `objective_draft_proposal()`** | [Tech §5.4] | `src/nexus/agents/objective.py`: **Pre-LLM programmatic adjustments (Tech §4.4):** before building the LLM prompt, adjust deterministic search parameters based on the rejection reason in `state["rejection_context"]`: logistics rejection → multiply `search_radius_miles` by 0.8; meteorology date rejection → shift `target_date` +1 day; family no-cell rejection → add `require_cell_coverage=True` to search params; logistics timeline conflict → compress time window by 30 min. These adjustments are Python code — not LLM instructions. After adjustments, fetch activity candidates via tool registry. Include rejection history in prompt for targeted revision (revision strategy matrix — Tech §4.4). Exclude already-proposed activity IDs from candidates list. Use `.with_structured_output(ActivityProposal)`. Return `primary_activity`, `proposal_history` (via append reducer), `current_phase="reviewing"`, `negotiation_log`. Wrap with `@agent_error_boundary("objective", is_hard_constraint=False)`. |
| 5.10 | **Implement `family_coordinator_review()`** | [Tech §5.6] | `src/nexus/agents/family_coordinator.py`: LOCKED LOCAL (ModelRouter enforces). Estimate cell coverage via heuristic. Search nearby places. LLM call uses `.with_structured_output(FamilyPlanVerdict)` (defined in task 1.6). Enforce hard constraint: teen + no cell service → override to REJECTED regardless of LLM verdict. Call `result.to_agent_verdict()` to produce the `AgentVerdict`. Return `current_verdicts`, `family_activities`, `negotiation_log`. Wrap with `@agent_error_boundary("family_coordinator", is_hard_constraint=True)`. **Spec code caution:** Tech §5.6 code uses dot notation (`state.family_profile`) — this is wrong for a TypedDict; use `state["family_profile"]` throughout. **MVP scope (PRD §8.1 F14 = P1):** acceptable nearby family option exists at all — per-member activity scoring and full matching is a P1 enhancement. Mark with a `TODO(P1):` comment. |
| 5.11 | **Implement `nutritional_review()`** | [Tech §5.7] | `src/nexus/agents/nutritional.py`: Search restaurants near endpoint. No restaurants → hard REJECTED (deterministic, no LLM call needed). LLM call uses `.with_structured_output(NutritionalVerdict)` (defined in task 1.6). Call `result.to_agent_verdict()` to produce the `AgentVerdict`. Return `current_verdicts`, `meal_plan`, `negotiation_log`. Wrap with `@agent_error_boundary("nutritional", is_hard_constraint=True)`. **MVP scope (PRD §8.1 F13 = P1):** dietary filter passes if a restaurant exists within range and the cuisine type overlaps dietary restrictions. Full macro optimization (protein_target_g matching) is P1. Mark with a `TODO(P1):` comment. |
| 5.12 | **Implement `plan_synthesizer()`** | [Tech §5.10] | `src/nexus/agents/synthesizer.py`: HYBRID — deterministic template data + LLM narrative prose. Call `prepare_llm_context(state)` for slimmed state. LLM generates narrative only (not facts/numbers). Call `render_plan_html()` and `render_plan_markdown()`. Generate backup plan from `proposal_history[-2]` if it exists; otherwise call `generate_relaxed_variant()` (widen one soft constraint, no extra LLM call). **`generate_relaxed_variant()` implementation spec:** define as a standalone function in `src/nexus/agents/synthesizer.py`. Signature: `def generate_relaxed_variant(state: WeekendPlanState) -> ActivityProposal`. Logic: copy `state["primary_activity"]` (shallow copy via `model_copy()`), then widen one soft constraint in priority order — (1) if `plan_requirements.max_distance_miles < 20`, increase by 5 miles; (2) elif `plan_requirements.min_elevation_gain_ft > 500`, reduce by 200 ft; (3) else set `has_exposed_sections=False` (choose a sheltered variant). Append `" (Relaxed)"` to `activity_name` to distinguish from the primary. Returns the modified `ActivityProposal` directly — no tool calls, no LLM call, no new data fetch. Return `output_html`, `output_markdown`, `current_phase="human_review"`, `backup_activity`. **Spec code note:** Tech §5.10 spec code omits `backup_activity` from the return dict — this is a spec bug; `backup_activity` must be returned to populate `WeekendPlanState`. **Dict-access reminder:** use `state["primary_activity"]`, never `state.primary_activity` — `WeekendPlanState` is a TypedDict. |
| 5.13 | **Implement `save_approved_plan()`** | [Tech §5.11] | `src/nexus/agents/save_plan.py`: Terminal node. Use `plan_filename()` to derive path. Write `output_markdown` to `~/.nexus/plans/`. Return `current_phase="completed"`. |
| 5.14 | **Implement `plan_filename()`** | [Tech §9.6] | `src/nexus/output/filenames.py`: Slugify activity name (strip special chars, replace spaces with hyphens, truncate to 30 chars). Format: `{date.isoformat()}-{slug}.md`. |
| 5.15 | Test LLM agents — schema validation only | [Tech §13.2] | `tests/test_agents/test_orchestrator.py`, `test_objective.py`, etc.: Mock the LLM call to return valid structured output. Assert output conforms to Pydantic model. Do NOT assert on specific LLM text — it varies. Test error boundary behavior on mock exceptions. |

**Validation:** All deterministic agents produce exact expected verdicts from known inputs. All LLM agents produce schema-valid output from mocked LLM responses. Error boundary correctly classifies failures. `just test-agents` passes.

---

## Phase 6 — Web Server, API, & WebSocket

**Goal:** FastAPI server running. All API endpoints functional. WebSocket streams progress in real-time.

### 6A — Server Foundation

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 6.1 | **Implement FastAPI app** | [Tech §9.2] | `src/nexus/web/server.py`: Create `FastAPI(title="Nexus", docs_url=None, redoc_url=None)`. Mount static files from `src/nexus/web/static/` via `app.mount("/static", StaticFiles(directory="..."), name="static")` — needed for favicon and any shared JS. Import all routes. Bind to `127.0.0.1` only — no network exposure. |
| 6.2 | **Implement API request/response schemas** | [Tech §9.5] | `src/nexus/web/schemas.py`: `PlanRequest`, `RejectRequest`, `ConstraintRequest`, `FeedbackRequest`, `PlanResponse`, `ApproveResponse`, `ApiKeyStatus`. All Pydantic models with `Literal` types for enums. |
| 6.3 | **Implement page routes** | [Tech §9.2, UX §4–9] | GET `/` (landing), GET `/preflight`, GET `/setup`, GET `/plan`, GET `/plans`, GET `/plans/{request_id}`. All return `HTMLResponse` via Jinja2. Redirect to `/preflight` if critical checks fail. Redirect to `/setup` if no profile. |
| 6.4 | **Implement API routes** | [Tech §9.2] | POST `/api/plans` (start planning — returns `PlanResponse` with `request_id`), POST `/api/plans/{id}/approve`, POST `/api/plans/{id}/reject`, POST `/api/plans/{id}/constraint`, POST `/api/plans/{id}/feedback`, POST `/api/setup`, POST `/api/setup/api-keys`, GET `/api/setup/api-keys/status`, GET `/api/preflight`. **WebSocket:** `GET /ws/plans/{request_id}` — must be an explicit route entry in the router, not just referenced inline. **Profile write:** `POST /api/setup` must use `ruamel.yaml` (not `yaml.dump`) to write `profile.yaml` — preserves user-added comments on round-trip. Import `from ruamel.yaml import YAML; yaml = YAML(); yaml.preserve_quotes = True`. |

### 6B — Graph Resume Logic (HITL)

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 6.5 | **Implement `approve_plan()`** | [Tech §8.3] | `src/nexus/web/routes.py`: Rebuild graph, compile with checkpointer, `ainvoke(None, config=thread_config)` to resume from interrupt. Returns final state. |
| 6.6 | **Implement `reject_plan()`** | [Tech §8.3] | Same file. `aupdate_state()` with `as_node="draft_proposal"` — injects feedback, resets `iteration_count=0`, clears `current_verdicts`. Then `ainvoke(None)` to resume. Increment `human_rejection_count`. Check rejection limits per PRD §6.4: 2 identical rejections → offer "go with this plan anyway"; 5 total → suggest manual planning. |
| 6.7 | **Implement mid-flight constraint injection** | [Tech §8.4] | POST `/api/plans/{id}/constraint`: `aupdate_state()` to append to `pending_constraints`. The `check_consensus` node drains this queue. WebSocket `/ws/plans/{id}` also accepts `{"type": "add_constraint", "text": "..."}`. |
| 6.8 | **Implement concurrency policy** | [Tech §9.8] | One active planning run per `request_id` — in-memory dict of active `asyncio.Lock` per request_id. Duplicate `POST /api/plans` with same active intent → `409 Conflict`. Approve/reject/constraint serialized via lock — first writer wins, concurrent attempts return `409`. **Restart caveat:** the in-memory lock dict is lost on server restart. If a plan is in-flight when the server restarts, the lock is gone but the LangGraph checkpoint persists in SQLite — the client can resume via the checkpoint; the lock absence is benign for a local-use tool. Document with a `# NOTE: locks are not persisted` comment in the code. |

### 6C — WebSocket Progress Streaming

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 6.9 | **Implement `PlanningProgress`** | [Tech §9.3] | `src/nexus/web/progress.py`: `on_node_start()`, `on_node_complete()`, `on_plan_ready()`, `on_planning_error()`. Each sends structured JSON with `event_id`, `stage`, `status`, `message`, `timestamp`. **`on_planning_error(error_type: str, message: str)`**: sends `{"event": "error", "event_id": ..., "error_type": error_type, "message": message, "timestamp": ...}` and is called when the error boundary catches an unrecoverable failure (Ollama crash, `HardConstraintDataUnavailable` with no fallback). Error events are stored in `_completed` and replayed on WebSocket reconnect. WebSocket connection stays open after error so the client can render the error state and offer `/preflight` link. |
| 6.10 | **Implement node-to-message mapping** | [Tech §9.3, UX §5.5] | `src/nexus/web/messages.py`: Map internal node names to user-facing copy per UX §5.5 progress copy map. `parse_intent` → "Understanding your request...", `review_meteorology` → "Checking {day} weather...", etc. Include iteration-aware messages for loop-back (UX §5.5 iteration table). |
| 6.11 | **Implement WebSocket reconnection** | [Tech §9.7] | On reconnect to `/ws/plans/{request_id}`: replay all `_completed` events. If `output_html` exists in state → send `plan_ready` immediately. Each event has unique `event_id` for client-side deduplication. |
| 6.12 | **Implement `stop_planning` WebSocket message** | [Tech §9.2, UX §5.2] | Client sends `{"type": "stop_planning"}`. Server cancels the current graph run and returns to input state. |
| 6.13 | **Wire graph execution to WebSocket** | — | In the planning API endpoint: create `PlanningProgress` and stream graph execution via `graph.astream_events(initial_state, config=thread_config, version="v2")` — **not** `.ainvoke()` (which blocks until completion). Consume the async generator: filter `event["event"] == "on_chain_start"` where `event["name"]` is a known node name → call `progress.on_node_start(event["name"])`; filter `"on_chain_end"` → call `progress.on_node_complete(event["name"])`. Unknown event names (LLM tokens, tool calls) are silently ignored. Run the entire streaming loop in `asyncio.create_task()` so the POST endpoint returns `PlanResponse` immediately; the WebSocket carries all subsequent updates. On `asyncio.CancelledError` (from `stop_planning`): call `progress.on_planning_error("cancelled", "Planning stopped by user")` and clean up the task. |

### 6D — API Key Management

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 6.14 | **Implement API key save endpoint** | [Tech §9.2] | POST `/api/setup/api-keys`: Accept `{"YELP_API_KEY": "..."}`. Write to `~/.nexus/.env`. Validate each key by making a test API call. Return `{"results": {"YELP_API_KEY": "valid"}}`. Never log keys. Never return key values in GET responses. |
| 6.15 | **Implement API key status endpoint** | [Tech §9.5] | GET `/api/setup/api-keys/status`: Return `{"keys": {"YELP_API_KEY": true, "HIKING_PROJECT_KEY": false}}`. Check `.env` file existence, never return values. |

### 6E — Usage Statistics

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 6.16 | **Implement usage statistics tracker** | [UX §9.4] | `src/nexus/stats.py`: SQLite table `plan_stats` with columns `request_id`, `planned_at`, `activity_type`, `approved` (bool), `approval_pass` (int — 1 = first-pass, 2 = second-pass, etc.). `record_plan_started(request_id, activity_type)`, `record_plan_approved(request_id, pass_number)`, `record_plan_rejected(request_id)`. DB at `~/.nexus/stats.db`. Use stdlib `sqlite3` — no ORM needed. |
| 6.17 | **Wire stats tracker to approve/reject routes** | [UX §9.4] | Call `record_plan_approved()` from the approve route (task 6.5) and `record_plan_rejected()` from the reject route (task 6.6). Call `record_plan_started()` from `POST /api/plans`. |
| 6.18 | **Implement stats query for landing page** | [UX §9.4] | `get_monthly_stats() -> dict`: query `plan_stats` for current calendar month — return `{"plans_this_month": int, "first_pass_approval_rate": float}`. Called by the `GET /` route handler and passed to `landing.html.j2`. Empty month returns `{"plans_this_month": 0, "first_pass_approval_rate": None}` (template shows empty state). |

**Validation:** `uv run nexus` starts server. Browser opens. API endpoints return correct responses. WebSocket streams mock progress events. Approve/reject resume graph correctly. `409` returned on concurrent writes.

---

## Phase 7 — HTML Templates & Plan Rendering

**Goal:** All pages render correctly. Plan output matches UX Spec wireframes. Data confidence labels display in footer.

### 7A — Base Templates & Design System

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 7.1 | **Create `base.html.j2`** | [UX §12] | Base layout: system font stack, CSS custom properties (all color tokens from UX §12.3 — light and dark mode), max-width 680px, responsive padding. Include `prefers-color-scheme: dark` media query. Include `prefers-reduced-motion` media query. Print styles (hide buttons, no shadows). |
| 7.2 | **Create CSS design system** | [UX §12.1–12.7] | Embedded CSS in base template: typography scale (UX §12.2), card styles, timeline CSS (UX §12.5), button styles (UX §12.6), print styles (UX §12.7). No CDN, no JS frameworks. All `rem`/`em` for text sizing (accessibility — UX §14.2). |

### 7B — Page Templates

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 7.3 | **Create `preflight.html.j2`** | [UX §13.2] | Checklist layout: ✔/✘/○ status for each check. Fix actions as copy-paste commands or clickable links. "Re-check" button (JS fetch to `/api/preflight`). Auto-redirect on all-pass. Gray out dependent checks (Ollama not installed → server/model show ○). |
| 7.4 | **Create `landing.html.j2`** | [UX §9.4] | Pending plan card (if exists), last weekend summary, monthly stats (plans count, approval rate). Planning input at bottom: text field + "Plan It →" button. Empty state: "No plans yet. Ready when you are." |
| 7.5 | **Create `setup.html.j2`** | [UX §4.2–4.3, §4.6] | Multi-step form: 6 blocks (About You, Preferred Activities, Home Base, Your Family, Preferences, API Keys). One block per view with Next/Back navigation. Inline validation. Dynamic family member add/remove. API key test button with live status. Privacy messaging: "Everything stays on your machine" (UX §4.2). Save to `profile.yaml` via POST `/api/setup`. **Returning-user flow (UX §4.6):** when `profile.yaml` already exists, the `/setup` route detects this and renders a summary view with quick-edit section buttons ("Edit My Details", "Edit Activities", "Edit Home Base", "Edit Family", "Edit Preferences", "Edit API Keys", "Re-run Full Setup"). Clicking a section button deep-links to that block's wizard step. This prevents forcing existing users through all 6 steps to change one thing. |
| 7.6 | **Create `planning.html.j2`** | [UX §5.1–5.2] | Input field at top. Progress area below: WebSocket-powered live updates. Mid-planning constraint input always visible below progress. "Stop planning" link. Plan renders inline below progress when ready. JS: WebSocket connection to `/ws/plans/{request_id}`, DOM updates for progress lines (◌ active → ✔ complete → ✘ failed), constraint injection via send. |
| 7.7 | **Create `plan.html.j2`** | [UX §6.2–6.4] | Full plan wireframe per UX §6.3: Header (day + date), Hero Card (activity name, stats bar, verdict strip with confidence labels), Why This Plan (2 subsections), Timeline (vertical with family names), Backup Plan (collapsed), Before You Go (checklist + emergency), Decision Buttons (APPROVE + NOT THIS), Footer (data confidence labels). Verdict strip colors: green/amber/fail per confidence. `(est.)` suffix for estimated data. `(Xhr cache)` suffix for cached data. |
| 7.8 | Create `plan.md.j2` | [Tech §14] | Markdown template for Obsidian sync. Same content as HTML but in Markdown format. Includes YAML frontmatter: `date`, `activity`, `status`, `request_id`. |
| 7.9 | **Create `history.html.j2`** | [UX §9.5] | List of past plans. Each shows: date, activity name, status (approved/pending), feedback status. Click → plan detail. Empty: "No trips to reflect on yet." |

### 7C — Plan Rendering Logic

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 7.10 | **Implement `render_plan_html()`** | [Tech §9.4] | `src/nexus/output/html.py`: Jinja2 `PackageLoader`. `render_plan_html(narrative, state)` → maps all state fields to template variables. Passes `compute_tradeoff_summary()`, `output_confidence_labels`. Filters: exclude agent names, confidence scores, iteration counts from template context (enforcing UX §1.3 invisible system contract). |
| 7.11 | **Implement `render_plan_markdown()`** | [Tech §14] | `src/nexus/output/markdown.py`: Same data as HTML but rendered to Markdown via `plan.md.j2`. Include YAML frontmatter (`date`, `activity`, `status`, `request_id`). Use the `Markdown` library (listed in Tech §2.1 as `python-markdown` — **the correct PyPI package name is `Markdown`**, imported as `import markdown`) for any inline Markdown-to-HTML conversion needed when a historical `.md` plan is displayed via `GET /plans/{id}`. The Jinja2 template produces the raw Markdown file; `markdown.markdown()` converts it back for web display. |
| 7.12 | Implement compromised plan rendering | [UX §6.5] | Verdict strip switches to amber background. "One thing we traded" → "What we couldn't do". Trade-off summary uses specific numbers. |
| 7.13 | Implement no-safe-plan rendering | [UX §6.6] | Separate template block: unsafe headline, blocking reasons, downscaled alternative suggestion, next-weekend forecast. Buttons: "PLAN THE LOOP HIKE" / "SKIP THIS WEEK". |

### 7D — Feedback Form

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 7.14 | **Implement feedback form** | [UX §8.2–8.5, §9.5] | Inline on plan detail page. 3 questions max: "How did it go?" (4 radio options), free-text "Anything to note?", conditional "What changed?" (on "Had to change things"). **Storage (UX §9.5):** feedback is **appended to the existing plan Markdown file** at `~/.nexus/plans/{date}-{slug}.md` as a `## Post-Trip Feedback` section — NOT saved to a separate YAML file. This keeps the full trip record (plan + feedback) in a single Obsidian-compatible Markdown file. `POST /api/plans/{id}/feedback` finds the plan file via `plan_filename()`, opens in append mode, writes the feedback block. Display warm acknowledgment with specific action ("We'll suggest earlier departure"). |
| 7.15 | Implement rejection feedback UI | [UX §7.1–7.4] | Inline below plan on reject: text input + REPLAN/CANCEL buttons. Required text (disable REPLAN until text entered). After submit: replanning progress streams in same page. Edge cases: identical feedback twice → offer "go with this plan anyway?"; 5 rejections → suggest manual planning (PRD §6.4). |
| 7.16 | **Implement HTML snapshot tests for plan templates** | [Tech §13] | `tests/test_output/test_html_render.py`: Render `plan.html.j2` with a fixture `WeekendPlanState` (approved plan, all fields populated). Save output to `tests/fixtures/plan_snapshot.html`. On subsequent runs, compare rendered output byte-for-byte to the saved snapshot (`assert rendered == snapshot`). Any template change that alters output fails until the snapshot is intentionally updated (delete and re-run). Also add a test that `render_plan_html()` raises `jinja2.UndefinedError` when required template variables are missing (`StrictUndefined` mode). These catch template regressions that unit tests miss. |

**Validation:** All pages render without errors. Plan output matches UX §6.3 wireframe structure. Verdict strip shows correct colors. Data confidence labels display in footer. Dark mode works. Print hides buttons. Feedback appended to plan Markdown file (not a separate YAML). Mobile viewport stacks buttons vertically. HTML snapshot test passes (baseline committed).

---

## Phase 8 — CLI Launcher & Preflight System

**Goal:** `nexus` command starts server and opens browser. `start.command` handles all prerequisites.

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 8.1 | **Implement Typer CLI app** | [Tech §9.1] | `src/nexus/cli/app.py`: `main()` callback (starts server + opens browser), `plan` command (starts with intent pre-loaded). `--port` option (default 7820), `--debug` option. Use `webbrowser.open()`. Use `uvicorn.run()` with `host="127.0.0.1"`, `log_level="warning"`. |
| 8.2 | **Implement preflight checks** | [Tech §9.1.1] | `src/nexus/cli/preflight.py`: `run_preflight(port)` → `PreflightResult`. Checks (fast→slow): port availability (socket test), Ollama installed (`shutil.which`), Ollama running (HTTP ping to 11434), model available (`ollama list` parsing), disk space (`os.statvfs`), RAM (`platform`-specific). Each check returns `CheckResult(name, status, message, fix_action, is_critical)`. `can_start = True` even if non-critical checks fail. **RAM check:** Python's `platform` module does NOT provide RAM info — use `import psutil; psutil.virtual_memory().available`. Add `psutil` to `[project.dependencies]` in `pyproject.toml` (not dev group — preflight runs at server launch, not only in tests). Threshold: warn (non-critical) if available RAM < 10GB (cannot fit 9B model); error (critical) if < 4GB. **Disk space threshold:** check free space at `config.paths.base_dir` via `os.statvfs`. Warn (non-critical) if < 15GB free; fix_action: `"Free space on the drive containing ~/.nexus"`. These thresholds assume the 9B model (~7GB) plus 500MB cache buffer. |
| 8.3 | **Create `start.command` / `start.sh`** | [Tech §15.3] | Repo root launcher script per Tech §15.3. Idempotent. Handles: uv install, `uv sync`, Ollama install (brew on macOS, install script on Linux), `ollama serve`, model pull, disk space check. Print ✔/✘ status for each step. End with `uv run nexus`. `start.command` is symlink to `start.sh` on macOS. |
| 8.4 | Test preflight | — | Mock `shutil.which`, subprocess calls. Test all-pass scenario. Test Ollama missing → fail. Test port busy → fallback. Test disk space warning. |

**Validation:** `uv run nexus` starts server, opens browser. `uv run nexus plan "beach day"` opens with planning started. `./start.command` from clean environment installs everything and launches. Preflight page shows correct status for simulated failures.

---

## Phase 9 — End-to-End Integration

**Goal:** Complete planning loop works: intent → agents → consensus → safety → human review → approve/reject. All LangGraph patterns demonstrated.

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 9.1 | **Wire agent functions to graph nodes** | [Tech §4.1] | In `graph/planner.py`, replace the Phase 4 stub functions with imports of the actual agent implementations from Phase 5. **Node name → function → module (all 10 nodes):** `"parse_intent"` → `orchestrator_parse_intent` (`agents/orchestrator.py`), `"draft_proposal"` → `objective_draft_proposal` (`agents/objective.py`), `"review_meteorology"` → `meteorology_review` (`agents/meteorology.py`), `"review_family"` → `family_coordinator_review` (`agents/family_coordinator.py`), `"review_nutrition"` → `nutritional_review` (`agents/nutritional.py`), `"review_logistics"` → `logistics_review` (`agents/logistics.py`), `"check_consensus"` → `orchestrator_check_consensus` (`agents/orchestrator.py`), `"review_safety"` → `safety_review` (`agents/safety.py`), `"synthesize_plan"` → `plan_synthesizer` (`agents/synthesizer.py`), `"save_plan"` → `save_approved_plan` (`agents/save_plan.py`). Update `src/nexus/agents/__init__.py` to re-export all. Run `just typecheck` to confirm all 10 nodes satisfy the `AgentNode` Protocol signature. |
| 9.2 | **Wire tool registry to agents** | [Tech §7.3] | Initialize `ToolRegistry` during server startup. **Singleton pattern (commit to this):** create `src/nexus/runtime.py` with module-level vars `tool_registry: ToolRegistry` and `model_router: ModelRouter`. Populate both in FastAPI's `lifespan` startup handler in `server.py` — `runtime.tool_registry = ToolRegistry(config)`. Agents import directly: `from nexus.runtime import tool_registry`. Tests override via `monkeypatch.setattr("nexus.runtime.tool_registry", mock_tool_registry)` in the `mock_tool_registry` fixture (conftest.py). This pattern is simpler than LangGraph config injection and avoids passing registry through the state dict. Ensure agents use `tool_registry.get("weather")` etc. |
| 9.3 | **Wire model router to agents** | [Tech §3.3] | Initialize `ModelRouter` during server startup. Uses the same `src/nexus/runtime.py` singleton pattern established in task 9.2 — `runtime.model_router = ModelRouter(config)`. LLM agents import: `from nexus.runtime import model_router`. Tests override via `monkeypatch.setattr("nexus.runtime.model_router", mock_model_router)`. Ensure `family_coordinator` always gets local model (enforced by `ModelRouter.LOCKED_LOCAL_AGENTS`). |
| 9.4 | **Implement latency budget enforcement** | [Tech §8.5] | Wrap LLM calls with `asyncio.wait_for(coro, timeout=15)` **at each call site in the LLM agent file** — e.g., `result = await asyncio.wait_for(structured_llm.ainvoke(prompt), timeout=15)` in `orchestrator.py`, `objective.py`, `family_coordinator.py`, `nutritional.py`, and `synthesizer.py`. Do NOT add timeout logic in `ModelRouter` (it only returns a model instance and makes no calls). Wrap node-level execution with appropriate timeouts: `draft_proposal` 25s, fan-out batch 25s, `synthesize_plan` 15s. On timeout: error boundary produces appropriate verdict. |
| 9.5 | **Implement 90-second planning time cap** | [PRD §6.5] | In `run_planning()`: wrap entire graph invocation with `asyncio.wait_for(coro, timeout=90)`. On timeout: force best current proposal through safety review, annotate with "planning time exceeded". |
| 9.6 | **Implement Ollama crash detection** | [Tech §12.2] | In `agent_error_boundary`: catch `httpx.ConnectError` to port 11434 → classify as `INTERNAL_ERROR`, send WebSocket error event, halt planning, link to `/preflight`. |
| 9.7 | **Validate backup plan generation end-to-end** | [Tech §16 Phase 7] | The backup plan implementation lives in task 5.12 (synthesizer). This task validates it works end-to-end: run a full plan with 3 proposals in `proposal_history` \u2192 confirm `backup_activity` is populated in final state \u2192 confirm `plan.html.j2` renders the backup section with a one-sentence difference summary \u2192 confirm no extra LLM call was made (mock LLM call count). Also test the `generate_relaxed_variant()` path: run with only 1 proposal in history \u2192 confirm backup is the relaxed variant. |
| 9.8 | **Implement debug logging** | [PRD §8.3] | When `--debug` flag is set: write full `negotiation_log` to `~/.nexus/logs/{timestamp}.log`. Never show in default output. |
| 9.9 | **E2E test with mocked APIs** | [Tech §13.1] | `tests/test_e2e/test_full_plan.py`: Full graph run with all external APIs mocked via `pytest-httpx`. Verify: graph starts, agents execute, consensus reached or max iterations, safety review runs, plan synthesized, checkpoint saved. Test rejection loop: reject → feedback injected → replan. Test mid-flight constraint: add constraint during planning → incorporated. |
| 9.10 | Verify LangGraph patterns table | [Tech §4.3] | Walk through every pattern in the table and verify it's demonstrable in the codebase: StateGraph construction, typed state, reducers, conditional edges, cyclical loop, Send API fan-out, SqliteSaver, interrupt_after, resume from interrupt, supervisor/worker, adversarial review, tool binding, structured output. **Stale table entry:** the patterns table in Tech §4.3 lists "Resume from interrupt → `cli/commands.py — approve_command()`" — this reference is stale (pre-ADR-6). The correct location is `web/routes.py — approve_plan()`. Verify the pattern using the correct file and ensure `docs/langgraph-patterns.md` (task 10.11) uses the corrected reference. |

**Validation:** Complete flow works with mocked APIs: `nexus` → browser → type intent → progress streams → plan renders → approve → Markdown saved. Rejection loop works. Mid-planning constraint works. Debug log written with `--debug`. E2E test passes. All 13 LangGraph patterns from Tech §4.3 are demonstrable.

---

## Phase 10 — Polish, Documentation & MVP Exit

**Goal:** First-time user experience is flawless. Documentation complete. All MVP exit criteria met.

### 10A — First-Use Experience Polish

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 10.1 | **Test first-time user journey** | [UX §3.1] | Fresh `~/.nexus/` — verify: `nexus` → browser → redirects to `/setup` → complete form → profile saved → redirects to landing → type intent → plan. Under 10 minutes total. |
| 10.2 | **Test weekly ritual journey** | [UX §3.2] | With existing profile: `nexus` → landing shows history → type intent → progress → plan → approve → "Have a great Sunday, Alex." → plan saved. Under 5 minutes active time. |
| 10.3 | **Test rejection journey** | [UX §3.3] | Reject with feedback → replan → revised plan reflects feedback. Test edge cases: empty feedback (blocked), identical feedback twice, 5 rejections. |
| 10.4 | **Test no-safe-plan journey** | [UX §3.4] | Simulate all-bad-weather → system shows no-safe-plan output with downscaled alternative and next-weekend suggestion. |
| 10.5 | Test stale cache journey | [UX §13.6] | Simulate API failure with cache → plan renders with `cached (X hours)` labels. Simulate no cache → hard constraint halts planning with clear message. |

### 10B — Output Quality Verification

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 10.6 | **Verify no system internals in output** | [UX §1.3, PRD §9.4] | Grep all templates and prompts for: agent names, "confidence", "iteration", "node", "graph", "LangGraph", "APPROVED", "REJECTED", "NEEDS_INFO", percentage scores. None should appear in user-facing output. This is a hard requirement — any leak is a bug. |
| 10.7 | **Verify copy rules** | [UX §10.1–10.3] | Voice check: no emoji, no "Sorry", no "I", no "the system". Family names used (not "your spouse"). Progress lines ≤ ~80 chars. Verdict strip ≤ 3 phrases. |
| 10.8 | **Verify plan content completeness** | [PRD §9.5] | Every approved plan includes all 9 required elements: activity stats, conditions verdict, why this plan, trade-off disclosure, full-day timeline, backup option, preparation checklist, emergency info, decision buttons. |

### 10C — Documentation

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 10.9 | Write `README.md` | [Tech §14] | Project overview, quickstart (both launcher and manual), screenshots/GIF of planning flow, architecture overview diagram, link to specs, contributing guide, license (MIT). |
| 10.10 | Write `CONTRIBUTING.md` | [Tech §14] | Dev setup, project structure overview, how to add a new provider (Protocol pattern), how to add a new agent, testing conventions, code style (ruff + pyright). |
| 10.11 | Write `docs/langgraph-patterns.md` | [Tech §4.3, 14] | Educational guide: walk through each of the 13 LangGraph patterns with Nexus code snippets. This is the showcase artifact — a LangGraph newcomer reads this and understands every pattern. **Spec correction:** the patterns table in Tech §4.3 lists "Resume from interrupt → `cli/commands.py — approve_command()`" — this reference is stale (pre-ADR-6 CLI-first design). The correct location is `web/routes.py — approve_plan()`. Use the corrected reference in this document. |
| 10.12 | Write `docs/ARCHITECTURE.md` | [Tech §14] | High-level overview for contributors: graph topology, agent classification, state flow, tool abstraction, HITL design. |

### 10D — MVP Exit Criteria Verification

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 10.13 | **Verify: End-to-end planning works** | [PRD §13.3] | `nexus` → browser → submit intent → valid plan for at least 3 distinct activity/date combinations (hiking, beach, city). |
| 10.14 | **Verify: All hard constraints enforced** | [PRD §13.3] | Zero hard-constraint violations across 10 consecutive test runs with varied inputs. |
| 10.15 | **Verify: Mid-planning input works** | [PRD §13.3] | Add constraint during planning → system incorporates without restarting. |
| 10.16 | **Verify: Rejection loop works** | [PRD §13.3] | Reject → feedback incorporated → revised plan reflects the feedback. |
| 10.17 | **Verify: Setup flow works** | [PRD §13.3] | Browser-based setup creates valid `profile.yaml` from scratch. No YAML editing required. |
| 10.18 | **Verify: Offline resilience** | [PRD §13.3] | System uses cached data when APIs unreachable. Plan has data-age annotations. Hard constraint with no cache halts with clear message. |
| 10.19 | **Verify: Plan archive works** | [PRD §13.3] | Approved plans saved as Markdown to `~/.nexus/plans/`. Obsidian-compatible. Feedback appended to the same file (not separate YAML). |
| 10.20 | **Verify: No internals exposed** | [PRD §13.3] | Output contains zero agent names, confidence scores, iteration counts, or architecture terms. |
| 10.21 | **Implement User Trust Score prompt** | [PRD §12.1] | After plan approval, show a single-question inline prompt: "How confident are you in this plan? (1–5)" with star-input or radio buttons. Optional (user can dismiss). Save score to the plan Markdown file's YAML frontmatter alongside `status: approved`. Target ≥ 4.0 per PRD §12.1. Requires no new infrastructure — `POST /api/plans/{id}/trust-score` writes one field to the plan file. |
| 10.22 | **Wire UX metrics to usage log** | [UX §15.1] | Ensure the stats tracker (task 6.16) captures the data points for UX §15.1 metrics: approval time (timestamp from `record_plan_started` to `record_plan_approved`), human rejection count per session (already in `WeekendPlanState`), feedback completion rate (feedback appended vs. plans approved). Add a `get_ux_metrics_summary()` function to `stats.py` that aggregates these for `--debug` reporting. No user-facing display required — this is internal instrumentation. |

**Validation:** All 8 MVP exit criteria (PRD §13.3) pass. All journeys (UX §3.1–3.4) work end-to-end. Documentation complete. `just check` passes. Ready for dogfooding.

---

## Dependency Graph

```
Phase 0 ─── Scaffolding
   │
Phase 1 ─── Config + State ──────────────────┐
   │                                          │
Phase 2 ─── LLM Router                       │
   │                                          │
Phase 3 ─── Tool Layer ──────────────┐        │
   │                                 │        │
Phase 4 ─── LangGraph Core ─────────┤        │
   │                                 │        │
Phase 5 ─── Agents ─────────────────┤        │
   │                                 │        │
Phase 6 ─── Web Server + API ───────┘        │
   │                                          │
Phase 7 ─── Templates + Rendering ───────────┘
   │
Phase 8 ─── CLI + Launcher
   │
Phase 9 ─── E2E Integration
   │
Phase 10 ── Polish + MVP Exit
```

Phases 2, 3, and 4 can be worked in parallel after Phase 1 is complete.
Phases 5 and 6 can be worked in parallel once their dependencies are met.
Phase 7 depends on Phase 6 (server) and Phase 1 (state schemas).
Phases 8–10 are sequential.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ollama structured output unreliable with chosen model | Agents produce malformed state → graph crash | Test with actual model early (Phase 2). Add retry with stricter format instruction (Tech §12.2). Consider `format="json"` mode. |
| OSRM public demo server rate-limited or down | Logistics agent fails repeatedly | Haversine fallback implemented in Phase 3 (Tech §7.5). Conservative estimate won't cause false hard-constraint violations. |
| Yelp API terms restrict use | No restaurant/menu data for nutritional agent | Overpass can find restaurants (no menus). Degrade nutritional agent to location-only check with `ESTIMATED` dietary compliance. |
| LangGraph API changes between versions | Graph construction code breaks | Pin `langgraph>=1.1.0,<2` in pyproject. Monitor releases. Integration tests catch breaks early. |
| 90-second planning cap too tight for cold caches | First run always exceeds cap → poor first experience | UX §5.6 handles this with "First run takes a bit longer" message. Tighten individual timeouts. Pre-warm cache during setup if possible. |
| Template rendering bugs cause plan output with missing data | User sees blank fields or template syntax | Test templates with fixture data in Phase 7. Jinja2 `undefined=StrictUndefined` to catch missing variables early. |

---

## Phase 11 — UX Redesign (Post-MVP Polish) ✅

**Goal:** Redesign all three web pages to a cleaner, purpose-built layout per UX Spec §1.7.0. Replace the original single-column cockpit with a launcher home, 2-zone planning cockpit, and editorial plan view.

| # | Task | Spec Ref | Details |
|---|------|----------|---------|
| 11.1 | **Rewrite `index.html.j2` — Launcher home** | [UX §11.1] | `body.launcher`. Centered full-screen layout. `h1` "Nexus" + subtitle. `#plan-form.launcher-form` (text input + "Plan It →"). Identity line ("Planning for {name}"). `.recent-plans` list. `.launcher-nav` top-right (System · Profile). |
| 11.2 | **Rewrite `planning.html.j2` — 2-zone cockpit** | [UX §5.2] | `body.cockpit`. `grid-template-columns: 42% 1fr`. Left: `#planning-graph` (SVG execution graph) + `#inputs-context` (request context). Right: `.context-hero#context-box` (status hero) + `.agent-queue#agent-grid` (compact scrollable agent trace rows) + `.steer-section` (always-visible constraint input). `#step-list` hidden for JS compat. `setContext()` updated to target `#context-hero-text`. |
| 11.3 | **Rewrite `plan.html.j2` — Editorial single column** | [UX §6.3] | `body.cockpit` (topbar/bottombar only) + `.plan-editorial` inner wrapper (max-width 720px, centred). Content order: `h1` → `.plan-meta-line.stats-bar` → `.plan-verdict-row.verdict-strip` → `<hr>` → why → day_narrative → timeline → checklist ("Before you go") → restaurant → backup → hidden panels. Fixed `.topbar` (← Nexus · date) and fixed `.bottombar` (✓ APPROVE · ✕ NOT THIS). |
| 11.4 | **Fix snapshot regression tests** | [Tech §13.2] | Deleted `tests/fixtures/plan_snapshot.html` (captured old 3-column layout). Re-ran test suite to regenerate baseline from new editorial template. Added `.stats-bar` and `.verdict-strip` as secondary CSS classes to satisfy `test_plan_template_has_all_required_sections`. Fixed checklist label casing: "Before you go" (lowercase). |

**Validation:** `uv run pytest --tb=short -q` → **204 passed, 0 failed**. All snapshot regression tests pass. All required section string tests pass.

*End of Implementation Plan*
