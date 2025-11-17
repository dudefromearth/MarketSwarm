#!/opt/homebrew/bin/bash
set -e

ROOT="$(pwd)"
echo "ROOT: $ROOT"

echo "▶ Running minimal setup..."
python3 services/rss_agg/setup.py

echo "▶ Running ingestion..."
python3 services/rss_agg/intel/ingestor.py