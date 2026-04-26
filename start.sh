#!/usr/bin/env bash
# start.sh — Nexus launcher script (Tech §15.3)
#
# Idempotent: safe to run multiple times.
# On macOS: symlinked as start.command (double-click to launch from Finder).
# On Linux: run directly with ./start.sh

set -euo pipefail

NEXUS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$NEXUS_DIR"

ok() { printf " ✔ %s\n" "$1"; }
fail() { printf " ✘ %s\n" "$1"; }
info() { printf " → %s\n" "$1"; }

echo ""
echo "  Nexus — Weekend Planning"
echo ""

# ── 1. Check uv ────────────────────────────────────────────────────────────
if command -v uv &>/dev/null; then
  ok "uv installed ($(uv --version 2>&1 | head -1))"
else
  fail "uv not installed"
  info "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# ── 2. Install dependencies ────────────────────────────────────────────────
info "Installing dependencies..."
if uv sync --all-extras -q; then
  ok "Dependencies installed"
else
  fail "Dependency install failed — run: uv sync --all-extras"
  exit 1
fi

# ── 3. Ollama ────────────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
  ok "Ollama installed"
else
  fail "Ollama not installed"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    info "Installing via Homebrew..."
    if command -v brew &>/dev/null; then
      brew install ollama --quiet && ok "Ollama installed via brew"
    else
      info "Install Homebrew first: https://brew.sh"
      info "Then: brew install ollama"
      exit 1
    fi
  else
    info "Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh"
    exit 1
  fi
fi

# ── 4. Start Ollama if not running ────────────────────────────────────────
export OLLAMA_USE_MLX=1          # enable Apple Silicon MLX backend
if ! nc -z 127.0.0.1 11434 2>/dev/null; then
  info "Starting Ollama with MLX backend..."
  ollama serve &>/dev/null &
  sleep 2
  if nc -z 127.0.0.1 11434 2>/dev/null; then
    ok "Ollama started"
  else
    fail "Could not start Ollama — run: ollama serve"
    exit 1
  fi
else
  ok "Ollama running"
fi

# ── 5. Pull model if needed ────────────────────────────────────────────────
MODEL="${NEXUS_MODEL:-qwen3:8b}"
if ollama list 2>/dev/null | grep -q "$MODEL"; then
  ok "Model $MODEL available"
else
  info "Pulling $MODEL (this may take several minutes on first run)..."
  ollama pull "$MODEL"
  ok "Model $MODEL ready"
fi

# ── 6. Disk space check ────────────────────────────────────────────────────
NEXUS_HOME="$HOME/.nexus"
mkdir -p "$NEXUS_HOME"
if command -v df &>/dev/null; then
  FREE_GB=$(df -g "$NEXUS_HOME" 2>/dev/null | tail -1 | awk '{print $4}')
  if [[ -n "$FREE_GB" && "$FREE_GB" -lt 15 ]]; then
    fail "Low disk space: ${FREE_GB}GB free (need ≥15GB)"
    info "Free space on the drive containing ~/.nexus"
    # Non-critical: proceed anyway
  else
    ok "Disk space OK (${FREE_GB:-?}GB free)"
  fi
fi

# ── 7. Launch Nexus ────────────────────────────────────────────────────────
echo ""
info "Starting Nexus..."
echo ""
exec uv run nexus "$@"
