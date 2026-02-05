#!/usr/bin/env python3
"""Run database migration for Journal service."""

import sys
from pathlib import Path

# Ensure MarketSwarm root is on sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.logutil import LogUtil
from shared.setup_base import SetupBase
from services.journal.intel.db_v2 import JournalDBv2

import asyncio


async def main():
    logger = LogUtil("journal-migration")
    logger.info("Starting database migration...", emoji="🗄️")

    # Load configuration
    setup = SetupBase("journal", logger)
    config = await setup.load()

    logger.info("Configuration loaded, initializing database...", emoji="📄")

    # Initialize DB - this triggers the migration
    db = JournalDBv2(config)

    logger.ok(f"Migration complete! Schema version: {db.SCHEMA_VERSION}", emoji="✅")


if __name__ == "__main__":
    asyncio.run(main())
