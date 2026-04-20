# Nexus

**Local-first weekend planning system powered by LangGraph and Ollama.**

Nexus turns a single sentence — *"hike somewhere cool this Sunday"* — into a fully vetted, family-safe plan: weather checked, driving times calculated, restaurant scouted, backup activity ready. Everything runs on your machine. No cloud. No subscriptions.

---

## Quickstart

### Option A — One-click launcher (macOS)

```
double-click  start.command
```

The launcher installs all prerequisites (uv, Ollama, model), then opens your browser.

### Option B — Manual

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Pull the local model
ollama pull qwen3:8b

# 4. Start Nexus
uv run nexus
```

Browser opens at `http://127.0.0.1:7820`. Follow the setup wizard on first run.

---

## Planning Flow

```
You:    "hike somewhere with the family this Sunday"
Nexus:  Checking Sunday weather...
        Scouting trail options...
        Reviewing family logistics...
        Finding a post-hike lunch spot...
        Running safety checks...
        ─────────────────────────────
        Here's your plan.
        [APPROVE]  [NOT THIS]
```

On approval, a Markdown file lands in `~/.nexus/plans/` — ready for Obsidian.

---

## Web Interface

Nexus has three pages, each designed for a distinct moment in the planning ritual:

**Launcher** (`/`) — the weekly entry point. Centered, full-screen form. Type one sentence; see your recent plans below.

**Planning cockpit** (`/plan?id=...`) — 2-zone live view during agent execution:
- **Left (42%):** SVG graph of the LangGraph execution showing each node's status in real time
- **Right (58%):** Context hero (active status), compact agent-trace queue, and a steer input always visible at the bottom for mid-planning constraints

**Plan view** (`/plans/{id}`) — single editorial column (720 px max-width), reading order:
`h1 title → stats bar → verdict chips → why this plan → day narrative → timeline → checklist → restaurant → backup plan → decision buttons (bottom bar)`

All three pages share the same design system (system fonts, CSS custom properties, dark mode, print styles). No CDN, no JavaScript frameworks.

---

## Architecture Overview

```
                ┌─────────────────────────────────────────────┐
                │              LangGraph Planning Graph        │
                │                                             │
  intent ──► parse_intent ──► draft_proposal ──► [fan-out]   │
                │                                    │        │
                │             ┌──────────────────────┤        │
                │             ▼          ▼           ▼        │
                │       meteorology  family      logistics     │
                │             │          │           │         │
                │             └──────────┴───────────┘        │
                │                        │                    │
                │                 check_consensus             │
                │               ┌────────┤                    │
                │               │ reject │ approve            │
                │               └──► draft_proposal           │
                │                        │                    │
                │                   review_safety             │
                │                        │                    │
                │                  synthesize_plan ◄── HITL   │
                │                        │        interrupt   │
                │                    save_plan                │
                └─────────────────────────────────────────────┘
```

**Key components:**

| Layer | Component | Purpose |
|-------|-----------|---------|
| Graph | `graph/planner.py` | StateGraph topology, routing, fan-out |
| Agents | `agents/` | 10 agent functions (deterministic + LLM) |
| Tools | `tools/providers/` | Weather, routing, activities, places |
| State | `state/graph_state.py` | Typed `WeekendPlanState` with reducers |
| Web | `web/routes.py` | FastAPI routes + WebSocket streaming |
| Output | `output/` | Jinja2 HTML + Markdown renderers |
| CLI | `cli/app.py` | Typer launcher + preflight checks |

---

## Requirements

- **macOS** 12+ or Linux (Ubuntu 22.04+)
- **Python** 3.12+
- **Ollama** (installed by `start.command` automatically)
- **RAM** ≥ 8 GB (16 GB recommended for `qwen3:8b`)
- **Disk** ≥ 15 GB free
- **Yelp API key** (optional, free tier — for restaurant search)

---

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Run only fast tests (no LLM, no network)
uv run pytest tests/ -k "not e2e" -v

# Lint + typecheck
uv run ruff check src/
uv run pyright src/

# All checks
just check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full dev guide.

---

## LangGraph Patterns

Nexus demonstrates 13 LangGraph patterns end-to-end. See [docs/langgraph-patterns.md](docs/langgraph-patterns.md) for annotated code walkthroughs.

---

## Configuration

First run prompts a browser-based setup wizard. Settings are stored in `~/.nexus/profile.yaml`. Comments you add are preserved on save.

Environment variables (optional):
```
YELP_API_KEY=your_key_here
```
Place in `~/.nexus/.env`. Never committed to git.

---

## Plan Archive

Approved plans are saved to `~/.nexus/plans/` as Markdown files:

```
~/.nexus/plans/
  2026-04-19-windy-hill-preserve.md
  2026-04-26-year-round-biking-on-the-bay.md
```

Each file includes YAML frontmatter (`date`, `activity`, `status`, `request_id`) and, optionally, a `## Post-Trip Feedback` section appended after the trip.

---

## License

GNU Affero General Public License v3.0 (AGPLv3). See [LICENSE](LICENSE).
