# Nexus justfile — all developer commands in one place.
# Usage: just <command>
# Install just: brew install just (macOS) or cargo install just

# Default: show available commands
default:
    @just --list

# ─── Run ────────────────────────────────────────────────────────────────────

# Start the Nexus server and open browser
run:
    uv run nexus

# Start with a pre-loaded planning intent
plan intent:
    uv run nexus plan "{{intent}}"

# ─── Test ───────────────────────────────────────────────────────────────────

# Run all tests
test:
    uv run pytest tests/ -v

# Run fast tests only (no LLM, no live APIs)
test-fast:
    uv run pytest tests/test_state/ tests/test_config.py -v

# Run agent tests
test-agents:
    uv run pytest tests/test_agents/ -v

# Run graph tests
test-graph:
    uv run pytest tests/test_graph/ -v

# Run tool provider tests
test-tools:
    uv run pytest tests/test_tools/ -v

# Run e2e tests (requires all phases implemented)
test-e2e:
    uv run pytest tests/test_e2e/ -v

# ─── Code Quality ───────────────────────────────────────────────────────────

# Lint and check for style issues
lint:
    uv run ruff check src/ tests/

# Auto-format code
format:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

# Static type checking
typecheck:
    uv run pyright src/

# Run lint + typecheck (CI gate)
check: lint typecheck

# ─── Ollama ────────────────────────────────────────────────────────────────

# Pull the default model (qwen3.5:9b)
ollama-pull:
    ollama pull qwen3.5:9b

# Check Ollama status and loaded models
ollama-status:
    @echo "=== Ollama running ==="
    @curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; tags=json.load(sys.stdin); [print(f'  {m[\"name\"]}') for m in tags.get('models',[])] or print('  (no models loaded)')" 2>/dev/null || echo "  Ollama not running — start with: ollama serve"

# ─── Setup ──────────────────────────────────────────────────────────────────

# Install all dependencies
install:
    uv sync --all-extras

# Create ~/.nexus directory structure
init-dirs:
    uv run python -c "from nexus.config import NexusConfig; from nexus.state.helpers import ensure_nexus_dirs; c=NexusConfig.load(); ensure_nexus_dirs(c)"
