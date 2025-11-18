#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm RSS Aggregator – Menu Launcher
###############################################

# Environment (safe)
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"
export PIPELINE_MODE="${PIPELINE_MODE:-full}"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="rss_agg"
MAIN="$ROOT/services/rss_agg/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

print_saved_urls() {
  clear
  line
  echo " Saved URLs in Redis (rss:category_links:*)"
  line
  echo ""

  CATEGORIES=$($BREW_REDIS -h 127.0.0.1 -p 6381 KEYS "rss:category_links:*")

  if [[ -z "$CATEGORIES" ]]; then
    echo "❌ No categories found in Redis."
    read -n 1 -s -r -p "Press any key to return to menu..."
    return
  fi

  for cat in $CATEGORIES; do
    echo "📂 Category: ${cat#rss:category_links:}"
    echo "---------------------------------------------"
    $BREW_REDIS -h 127.0.0.1 -p 6381 SMEMBERS "$cat"
    echo ""
  done | less

  echo ""
  read -n 1 -s -r -p "Press any key to return to menu..."
}

menu() {
  clear
  line
  echo " MarketSwarm – RSS Aggregator Launcher"
  line
  echo "Select Option:"
  echo ""
  echo "  1) FULL PIPELINE"
  echo "  2) Ingest Only       (RSS → category URL sets)"
  echo "  3) Canonical Only    (URL → canonical article)"
  echo "  4) Raw Fetch Only    (browser HTML fetch)"
  echo "  5) Enrich Only       (LLM enrichment)"
  echo "  6) Publish Only      (RSS XML generation)"
  echo "  7) View Saved URLs   (Redis category sets)"
  echo "  8) Quit"
  line
  read -rp "Enter choice [1-8]: " CH
  echo ""

  case "$CH" in
    1) export PIPELINE_MODE="full" ;;
    2) export PIPELINE_MODE="ingest_only" ;;
    3) export PIPELINE_MODE="canonical_only" ;;
    4) export PIPELINE_MODE="fetch_only" ;;
    5) export PIPELINE_MODE="enrich_only" ;;
    6) export PIPELINE_MODE="publish_only" ;;
    7) print_saved_urls; menu ;;
    8) echo "Goodbye"; exit 0 ;;
    *) echo "Invalid selection"; sleep 1; menu ;;
  esac
}

###############################################
# If argument provided, override menu
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    full|ingest_only|canonical_only|fetch_only|enrich_only|publish_only)
      export PIPELINE_MODE="$1"
      ;;
    show_urls)
      print_saved_urls
      exit 0
      ;;
    *)
      echo "❌ Invalid argument: $1"
      echo "Usage: $0 [full|ingest_only|canonical_only|fetch_only|enrich_only|publish_only|show_urls]"
      exit 1
      ;;
  esac
else
  menu
fi

###############################################
# Bootstrap Environment
###############################################
line
echo " RSS Aggregator Service Runner (Brew)"
line
echo "ROOT: $ROOT"
echo "MODE: $PIPELINE_MODE"
echo ""

if [[ ! -x "$BREW_PY" ]]; then
  echo "❌ Brew Python missing: $BREW_PY"
  exit 1
fi
echo "✔ Brew Python located"

if [[ ! -d "$VENV" ]]; then
  echo "❌ Missing virtualenv at $VENV"
  exit 1
fi
echo "✔ Virtualenv OK"

if [[ ! -x "$VENV_PY" ]]; then
  echo "❌ Missing venv python: $VENV_PY"
  exit 1
fi
echo "✔ venv Python OK"

if [[ ! -x "$BREW_REDIS" ]]; then
  echo "❌ redis-cli missing at $BREW_REDIS"
  exit 1
fi
echo "✔ Brew redis-cli OK"

echo "▶ Checking truth in system-redis…"
HAS_TRUTH="$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)"

if [[ "$HAS_TRUTH" -eq 0 ]]; then
  echo "❌ Missing truth document in system-redis"
  exit 1
fi
echo "✔ truth exists"

###############################################
# Launch orchestrator
###############################################
line
echo "🚀 Launching RSS Aggregator (MODE=$PIPELINE_MODE)"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"