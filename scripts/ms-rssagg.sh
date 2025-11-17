#!/opt/homebrew/bin/bash
set -euo pipefail

# ──────────────────────────────────────────────
# Environment (inject API keys for rss_agg here)
# ──────────────────────────────────────────────

export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
# If future models require org/project:
# export OPENAI_ORG="your-org"
# export OPENAI_PROJECT="your-project"

# Continue with your existing script
# ──────────────────────────────────────────────

# --- Brew Paths ---
BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

# --- Workspace ---
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="rss_agg"
MAIN="$ROOT/services/rss_agg/main.py"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

echo "──────────────────────────────────────────────"
echo " RSS Aggregator Service Runner (Brew)"
echo "──────────────────────────────────────────────"
echo "ROOT: $ROOT"
echo ""

# -------------------------------------------------
# 0) Validate Homebrew Python
# -------------------------------------------------
if [ ! -x "$BREW_PY" ]; then
  echo "❌ Brew Python not found at $BREW_PY"
  echo "   Install with: brew install python@3.14"
  exit 1
fi
echo "✔ Found Brew Python: $BREW_PY"

# -------------------------------------------------
# 1) Ensure venv exists
# -------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "❌ Virtualenv missing at $VENV"
  echo "   Create it with:"
  echo "      $BREW_PY -m venv .venv"
  exit 1
fi

echo "✔ Virtualenv present"

# -------------------------------------------------
# 2) Ensure venv Python exists
# -------------------------------------------------
if [ ! -x "$VENV_PY" ]; then
  echo "❌ venv Python missing at: $VENV_PY"
  exit 1
fi

echo "✔ venv Python: $VENV_PY"

# -------------------------------------------------
# 3) Validate Brew Redis CLI
# -------------------------------------------------
if [ ! -x "$BREW_REDIS" ]; then
  echo "❌ redis-cli (Homebrew) not found at $BREW_REDIS"
  echo "   Install with: brew install redis"
  exit 1
fi
echo "✔ Found Brew redis-cli: $BREW_REDIS"

# -------------------------------------------------
# 4) Check for truth
# -------------------------------------------------
echo "▶ Checking truth in system-redis…"
HAS_TRUTH="$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)"

if [ "$HAS_TRUTH" -eq 0 ]; then
  echo "❌ No truth document found in system-redis (key: truth)"
  echo "   Load truth with: scripts/ms-truth.sh load"
  exit 1
fi

echo "✔ truth.json found in system-redis:6379"
echo ""

# -------------------------------------------------
# 5) Export environment
# -------------------------------------------------
export SERVICE_ID="$SERVICE"
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

echo "✔ Environment configured"
echo ""

# -------------------------------------------------
# 6) Launch main.py using venv + Brew Python
# -------------------------------------------------
echo "🚀 Launching RSS Aggregator (brew-centric) ..."
echo "──────────────────────────────────────────────"
exec "$VENV_PY" "$MAIN"