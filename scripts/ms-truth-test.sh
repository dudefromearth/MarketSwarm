#!/opt/homebrew/bin/bash
set -euo pipefail

# --------------------------------------------------------------------
# 1. Load ms-busses.env from CURRENT DIRECTORY ONLY
# --------------------------------------------------------------------
if [[ ! -f "./ms-busses.env" ]]; then
  echo "[ERROR] ms-busses.env not found in current directory: $(pwd)" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "./ms-busses.env"

# --------------------------------------------------------------------
# 2. Validate required vars
# --------------------------------------------------------------------
for var in MS_ROOT TRUTH_JSON_PATH REDIS_CLI_PATH REDIS_SYSTEM_PORT; do
  if [[ -z "${!var:-}" ]]; then
    echo "[ERROR] $var not defined in ms-busses.env" >&2
    exit 1
  fi
done

# --------------------------------------------------------------------
# 3. Collect runtime values
# --------------------------------------------------------------------
REDIS_CLI="${REDIS_CLI_PATH}"
HOST="127.0.0.1"
PORT="${REDIS_SYSTEM_PORT}"
DB=0
PASS="${REDIS_SYSTEM_PASS}"
KEY="truth"
TRUTH_FILE="${TRUTH_JSON_PATH}"

# --------------------------------------------------------------------
# 4. Load truth file into Redis
# --------------------------------------------------------------------
echo "Loading truth from: ${TRUTH_FILE}"
echo "Into Redis: ${HOST}:${PORT}, DB=${DB}, Key=${KEY}"

${REDIS_CLI} -h "${HOST}" -p "${PORT}" -n "${DB}" SET "${KEY}" "$(cat "${TRUTH_FILE}")" >/dev/null

echo "Load complete."

# --------------------------------------------------------------------
# 5. Verify key exists and matches file contents
# --------------------------------------------------------------------
echo "Verifying truth key..."

REDIS_VAL="$(${REDIS_CLI} -h "${HOST}" -p "${PORT}" -n "${DB}" GET "${KEY}")"
FILE_VAL="$(cat "${TRUTH_FILE}")"

if [[ -z "${REDIS_VAL}" ]]; then
  echo "[FAIL] truth key NOT present in Redis."
  exit 1
fi

# Compare raw text exactly
if [[ "${REDIS_VAL}" == "${FILE_VAL}" ]]; then
  echo "[OK] truth value matches truth.json exactly."
else
  echo "[FAIL] truth value does NOT match truth.json."
  exit 1
fi

# --------------------------------------------------------------------
# 6. Validate system bus endpoint (PING check)
# --------------------------------------------------------------------
echo "Validating system-redis endpoint..."

PING_OUT="$(${REDIS_CLI} -h "${HOST}" -p "${PORT}" -n "${DB}" PING 2>/dev/null || true)"

if [[ "${PING_OUT}" == "PONG" ]]; then
  echo "[OK] Endpoint responsive (PONG)."
else
  echo "[FAIL] Endpoint did NOT respond with PONG."
  exit 1
fi

echo "All validation checks passed."