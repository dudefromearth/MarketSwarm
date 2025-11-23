# start-admin.sh
#!/bin/bash
cd /Users/ernie/MarketSwarm
source .venv/bin/activate
nohup python scripts/admin_server.py >> logs/admin.log 2>&1 &
echo $! > pids/admin.pid