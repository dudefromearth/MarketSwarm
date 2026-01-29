#!/bin/bash

############################################
# CONFIGURATION
############################################

LOCAL_DIR="/Users/ernie/Sites/feeds"
REMOTE_DIR="/public_html/feeds"

HOST="45.89.206.153"
USER="u452362222.flyonthewall.ai"
PASS="Adw3r4Zur!"

LOG_DIR="/Users/ernie/MarketSwarm/logs/feeds"
LOG_FILE="$LOG_DIR/feeds_sync.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

############################################
# FUNCTIONS
############################################

sync_feeds() {
  echo "[$(date)] Starting full feed sync..." | tee -a "$LOG_FILE"

  lftp -u "$USER","$PASS" ftp://$HOST <<EOF >> "$LOG_FILE" 2>&1
set ftp:ssl-allow no
set net:max-retries 2
set net:timeout 10
set xfer:clobber on
mirror -R --delete --verbose "$LOCAL_DIR" "$REMOTE_DIR"
bye
EOF

  if [ $? -eq 0 ]; then
    echo "[$(date)] Sync completed successfully." | tee -a "$LOG_FILE"
  else
    echo "[$(date)] Sync FAILED." | tee -a "$LOG_FILE"
  fi
}

show_status() {
  echo "========== STATUS =========="
  echo "Local directory : $LOCAL_DIR"
  echo "Remote directory: ftp://$HOST$REMOTE_DIR"
  echo "Log file        : $LOG_FILE"
  echo "Last 10 log lines:"
  echo "-----------------------------"
  tail -n 10 "$LOG_FILE"
  echo "============================"
}

test_connection() {
  echo "Testing FTP connection..."
  lftp -u "$USER","$PASS" ftp://$HOST <<EOF
set ftp:ssl-allow no
ls
bye
EOF
}

############################################
# AUTO-RUN WHEN NON-INTERACTIVE (CRON)
############################################

if [ ! -t 0 ]; then
  sync_feeds
  exit 0
fi

############################################
# MENU (INTERACTIVE ONLY)
############################################

while true; do
  clear
  echo "========================================="
  echo "  Feed Sync Manager"
  echo "========================================="
  echo "1) Sync feeds now"
  echo "2) Test FTP connection"
  echo "3) Show sync status"
  echo "4) Exit"
  echo "-----------------------------------------"
  read -p "Choose an option: " choice

  case $choice in
    1)
      sync_feeds
      read -p "Press Enter to continue..."
      ;;
    2)
      test_connection
      read -p "Press Enter to continue..."
      ;;
    3)
      show_status
      read -p "Press Enter to continue..."
      ;;
    4)
      echo "Exiting."
      exit 0
      ;;
    *)
      echo "Invalid option."
      sleep 1
      ;;
  esac
done