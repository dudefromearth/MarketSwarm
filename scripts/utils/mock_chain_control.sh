#!/opt/homebrew/bin/bash
set -euo pipefail

REDIS_HOST="127.0.0.1"
REDIS_PORT="6380"
REDIS_CLI="redis-cli -h $REDIS_HOST -p $REDIS_PORT"

CURRENT_UNDERLYING=""
CURRENT_EXPIRY=""

# ------------------------------------------------------------
# Optional: detect mock_massive PID (for USR1 only)
# ------------------------------------------------------------
get_mock_pid() {
  pgrep -f "mock_massive/main.py" || true
}

# ------------------------------------------------------------
# Discover available underlyings
# ------------------------------------------------------------
list_underlyings() {
  $REDIS_CLI --scan --pattern "massive:chain:latest:*:*" \
    | awk -F: '{print $4}' \
    | sort -u
}

select_underlying() {
  mapfile -t underlyings < <(list_underlyings)

  if [ "${#underlyings[@]}" -eq 0 ]; then
    echo "No underlyings found in Redis"
    sleep 2
    return
  fi

  clear
  echo "Available Underlyings:"
  echo "──────────────────────"
  for i in "${!underlyings[@]}"; do
    printf "  %d) %s\n" "$((i+1))" "${underlyings[$i]}"
  done
  echo ""
  read -rp "Select underlying [1-${#underlyings[@]}]: " choice

  if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#underlyings[@]} )); then
    CURRENT_UNDERLYING="${underlyings[$((choice-1))]}"
    CURRENT_EXPIRY=""
  else
    echo "Invalid selection"
    sleep 1
  fi
}

# ------------------------------------------------------------
# Discover expirations for selected underlying
# ------------------------------------------------------------
list_expirations() {
  $REDIS_CLI --scan --pattern "massive:chain:latest:${CURRENT_UNDERLYING}:*" \
    | awk -F: '{print $5}' \
    | sort -u
}

select_expiry() {
  if [ -z "$CURRENT_UNDERLYING" ]; then
    echo "Select an underlying first"
    sleep 2
    return
  fi

  mapfile -t expiries < <(list_expirations)

  if [ "${#expiries[@]}" -eq 0 ]; then
    echo "No expirations found for $CURRENT_UNDERLYING"
    sleep 2
    return
  fi

  clear
  echo "Available DTEs for $CURRENT_UNDERLYING:"
  echo "────────────────────────────────────"
  for i in "${!expiries[@]}"; do
    printf "  %d) DTE %d → %s\n" "$((i+1))" "$i" "${expiries[$i]}"
  done
  echo ""
  read -rp "Select DTE [1-${#expiries[@]}]: " choice

  if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#expiries[@]} )); then
    CURRENT_EXPIRY="${expiries[$((choice-1))]}"
  else
    echo "Invalid selection"
    sleep 1
  fi
}

# ------------------------------------------------------------
# Inspect selected chain snapshot
# ------------------------------------------------------------
check_chain() {
  if [ -z "$CURRENT_UNDERLYING" ] || [ -z "$CURRENT_EXPIRY" ]; then
    echo "Select both underlying and DTE first"
    sleep 2
    return
  fi

  latest_key="massive:chain:latest:${CURRENT_UNDERLYING}:${CURRENT_EXPIRY}"

  snapshot_key=$($REDIS_CLI GET "$latest_key" || true)
  if [ -z "$snapshot_key" ]; then
    echo "No snapshot pointer found:"
    echo "  $latest_key"
    return
  fi

  raw=$($REDIS_CLI GET "$snapshot_key" || true)
  if [ -z "$raw" ]; then
    echo "Snapshot missing or expired:"
    echo "  $snapshot_key"
    return
  fi

  ts=$(echo "$raw" | jq -r '.ts')
  atm=$(echo "$raw" | jq -r '.atm')
  range_points=$(echo "$raw" | jq -r '.range_points')
  total=$(echo "$raw" | jq '.contracts | length')
  calls=$(echo "$raw" | jq '[.contracts[] | select(.details.contract_type=="call")] | length')
  puts=$(echo "$raw" | jq '[.contracts[] | select(.details.contract_type=="put")] | length')

  call_min=$(echo "$raw" | jq '[.contracts[] | select(.details.contract_type=="call") | .details.strike_price] | min')
  call_max=$(echo "$raw" | jq '[.contracts[] | select(.details.contract_type=="call") | .details.strike_price] | max')
  put_min=$(echo "$raw" | jq '[.contracts[] | select(.details.contract_type=="put") | .details.strike_price] | min')
  put_max=$(echo "$raw" | jq '[.contracts[] | select(.details.contract_type=="put") | .details.strike_price] | max')

  total_oi=$(echo "$raw" | jq '[.contracts[] | .open_interest] | add // 0')
  total_vol=$(echo "$raw" | jq '[.contracts[] | .day.volume] | add // 0')

  echo "Current Chain Evidence:"
  echo "──────────────────────"
  echo "  Underlying     : $CURRENT_UNDERLYING"
  echo "  Expiry         : $CURRENT_EXPIRY"
  echo "  Latest Key     : $latest_key"
  echo "  Snapshot Key   : $snapshot_key"
  echo "  Timestamp      : $ts"
  echo "  ATM Strike     : $atm"
  echo "  Range Points   : $range_points"
  echo "  Total Contracts: $total"
  echo "  Calls          : $calls"
  echo "  Puts           : $puts"
  echo "  Call Range     : $call_min → $call_max"
  echo "  Put Range      : $put_min → $put_max"
  echo "  Total OI       : $total_oi"
  echo "  Total Volume   : $total_vol"
}

# ------------------------------------------------------------
# Interactive menu
# ------------------------------------------------------------
menu() {
  while true; do
    clear
    echo "──────────────────────────────────────────────"
    echo " MarketSwarm – chain snapshot inspector"
    echo "──────────────────────────────────────────────"
    echo ""

    mock_pid=$(get_mock_pid)
    if [ -n "$mock_pid" ]; then
      echo "mock_massive running (PID $mock_pid)"
    else
      echo "mock_massive not running (live Massive OK)"
    fi

    echo "Selected Underlying: ${CURRENT_UNDERLYING:-<none>}"
    echo "Selected Expiry   : ${CURRENT_EXPIRY:-<none>}"
    echo ""
    echo "Actions:"
    echo "  u) Select Underlying"
    echo "  e) Select DTE / Expiry"
    echo "  n) Next Chain (USR1 → mock_massive only)"
    echo "  c) Check Current Chain"
    echo "  s) Status"
    echo "  q) Quit"
    echo ""
    read -rp "Choose [u,e,n,c,s,q]: " choice

    case "$choice" in
      u|U) select_underlying ;;
      e|E) select_expiry ;;
      n|N)
        if [ -z "$mock_pid" ]; then
          echo "mock_massive not running — cannot send USR1"
          sleep 1
        else
          kill -USR1 "$mock_pid"
          echo "Sent USR1 — next mock chain published"
          sleep 1
        fi
        ;;
      c|C)
        check_chain
        read -rp "Press Enter..."
        ;;
      s|S)
        echo "Redis: $REDIS_HOST:$REDIS_PORT"
        sleep 2
        ;;
      q|Q) exit 0 ;;
      *)
        echo "Invalid choice"
        sleep 1
        ;;
    esac
  done
}

menu