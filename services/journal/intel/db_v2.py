# services/journal/intel/db_v2.py
"""MySQL database operations for the FOTW Trade Log system (v2)."""

import mysql.connector
from mysql.connector import pooling
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models_v2 import (
    TradeLog, Trade, TradeEvent, EquityPoint, DrawdownPoint, Symbol, Setting,
    JournalEntry, JournalRetrospective, JournalTradeRef, JournalAttachment,
    PlaybookEntry, PlaybookSourceRef, Tag, Alert,
    PromptAlert, PromptAlertVersion, ReferenceStateSnapshot, PromptAlertTrigger
)


class JournalDBv2:
    """MySQL database manager for FOTW trade logs."""

    SCHEMA_VERSION = 10

    # Default symbols with multipliers
    DEFAULT_SYMBOLS = [
        # Index Options
        {'symbol': 'SPX', 'name': 'S&P 500 Index', 'asset_type': 'index_option', 'multiplier': 100},
        {'symbol': 'NDX', 'name': 'Nasdaq 100 Index', 'asset_type': 'index_option', 'multiplier': 100},
        {'symbol': 'RUT', 'name': 'Russell 2000 Index', 'asset_type': 'index_option', 'multiplier': 100},
        {'symbol': 'XSP', 'name': 'Mini-SPX', 'asset_type': 'index_option', 'multiplier': 100},
        {'symbol': 'VIX', 'name': 'CBOE Volatility Index', 'asset_type': 'index_option', 'multiplier': 100},
        # ETF Options
        {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF', 'asset_type': 'etf_option', 'multiplier': 100},
        {'symbol': 'QQQ', 'name': 'Invesco QQQ Trust', 'asset_type': 'etf_option', 'multiplier': 100},
        {'symbol': 'IWM', 'name': 'iShares Russell 2000', 'asset_type': 'etf_option', 'multiplier': 100},
        {'symbol': 'DIA', 'name': 'SPDR Dow Jones', 'asset_type': 'etf_option', 'multiplier': 100},
        # Futures
        {'symbol': 'ES', 'name': 'E-mini S&P 500', 'asset_type': 'future', 'multiplier': 50},
        {'symbol': 'MES', 'name': 'Micro E-mini S&P 500', 'asset_type': 'future', 'multiplier': 5},
        {'symbol': 'NQ', 'name': 'E-mini Nasdaq 100', 'asset_type': 'future', 'multiplier': 20},
        {'symbol': 'MNQ', 'name': 'Micro E-mini Nasdaq', 'asset_type': 'future', 'multiplier': 2},
        {'symbol': 'RTY', 'name': 'E-mini Russell 2000', 'asset_type': 'future', 'multiplier': 50},
        {'symbol': 'YM', 'name': 'E-mini Dow', 'asset_type': 'future', 'multiplier': 5},
        {'symbol': 'CL', 'name': 'Crude Oil', 'asset_type': 'future', 'multiplier': 1000},
        {'symbol': 'GC', 'name': 'Gold', 'asset_type': 'future', 'multiplier': 100},
        # Common Stocks (placeholder - users can add more)
        {'symbol': 'AAPL', 'name': 'Apple Inc', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'TSLA', 'name': 'Tesla Inc', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'NVDA', 'name': 'NVIDIA Corp', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'AMD', 'name': 'Advanced Micro Devices', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'AMZN', 'name': 'Amazon.com Inc', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'GOOGL', 'name': 'Alphabet Inc', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'META', 'name': 'Meta Platforms', 'asset_type': 'stock', 'multiplier': 100},
        {'symbol': 'MSFT', 'name': 'Microsoft Corp', 'asset_type': 'stock', 'multiplier': 100},
    ]

    # Default example tags for new users (vocabulary seeds)
    # Organized by: Behavior, Context, Process, Insight
    # These are behavioral, contextual, non-judgmental, non-outcome-based
    DEFAULT_TAGS = [
        # A. Behavior & Decision Quality - train self-awareness without shame
        {'name': 'overtrading', 'description': 'Took more trades than planned'},
        {'name': 'forced trade', 'description': 'Entered without clear thesis'},
        {'name': 'late entry', 'description': 'Hesitated, entered after optimal point'},
        {'name': 'early exit', 'description': 'Closed before thesis played out'},
        {'name': 'hesitation', 'description': 'Delayed action when signal was clear'},
        {'name': 'impatience', 'description': 'Rushed into or out of position'},
        {'name': 'conviction trade', 'description': 'High confidence, sized appropriately'},
        {'name': 'stayed disciplined', 'description': 'Followed the plan despite pressure'},

        # B. Context & Environment - teach thinking in regimes
        {'name': 'volatility mismatch', 'description': "Strategy didn't match vol regime"},
        {'name': 'regime shift', 'description': 'Market character changed mid-trade'},
        {'name': 'thin liquidity', 'description': 'Slippage or poor fills due to low volume'},
        {'name': 'event-driven', 'description': 'Trade around scheduled catalyst'},
        {'name': 'post-news distortion', 'description': 'Price action skewed by recent news'},
        {'name': 'compressed volatility', 'description': 'Low vol environment, premium cheap'},
        {'name': 'expanding volatility', 'description': 'Rising vol, premium expensive'},

        # C. Process & Execution - anchor routine and mechanics
        {'name': 'thesis drift', 'description': 'Changed rationale mid-trade'},
        {'name': 'ignored context', 'description': 'Traded against broader conditions'},
        {'name': 'followed process', 'description': 'Executed according to plan'},
        {'name': 'broke rules', 'description': 'Deviated from established guidelines'},
        {'name': 'sizing issue', 'description': 'Position size was inappropriate'},
        {'name': 'risk misread', 'description': 'Misjudged the risk/reward'},

        # D. Insight & Learning Moments - reinforce positive pattern recognition
        {'name': 'clarity moment', 'description': 'Saw something clearly for the first time'},
        {'name': 'pattern recognized', 'description': 'Identified a recurring setup'},
        {'name': 'lesson learned', 'description': 'Key takeaway worth remembering'},
        {'name': 'worked as expected', 'description': 'Outcome matched thesis'},
        {'name': 'failed as expected', 'description': 'Loss was within anticipated scenario'},
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = {}

        self._pool = pooling.MySQLConnectionPool(
            pool_name="journal_pool",
            pool_size=5,
            host=config.get('JOURNAL_MYSQL_HOST', 'localhost'),
            port=int(config.get('JOURNAL_MYSQL_PORT', 3306)),
            user=config.get('JOURNAL_MYSQL_USER', 'journal'),
            password=config.get('JOURNAL_MYSQL_PASSWORD', ''),
            database=config.get('JOURNAL_MYSQL_DATABASE', 'journal'),
            charset='utf8mb4',
            autocommit=False
        )
        self._init_schema()

    def _get_conn(self):
        """Get a database connection from the pool."""
        return self._pool.get_connection()

    def _row_to_dict(self, cursor, row) -> Dict[str, Any]:
        """Convert a row tuple to a dictionary using cursor description."""
        if row is None:
            return None
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))

    def _get_schema_version(self, conn) -> int:
        """Get current schema version from database."""
        cursor = conn.cursor()
        try:
            # Check if schema_version table exists
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE() AND table_name = 'schema_version'
            """)
            if cursor.fetchone()[0] == 0:
                return 0
            cursor.execute("SELECT version FROM schema_version")
            row = cursor.fetchone()
            return row[0] if row else 0
        except mysql.connector.Error:
            return 0
        finally:
            cursor.close()

    def _set_schema_version(self, conn, version: int):
        """Set schema version in database."""
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("DELETE FROM schema_version")
            cursor.execute("INSERT INTO schema_version (version) VALUES (%s)", (version,))
        finally:
            cursor.close()

    def _table_exists(self, conn, table_name: str) -> bool:
        """Check if a table exists in the database."""
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE() AND table_name = %s
            """, (table_name,))
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()

    def _init_schema(self):
        """Initialize or migrate the database schema."""
        conn = self._get_conn()
        try:
            current_version = self._get_schema_version(conn)

            if current_version < 2:
                self._migrate_to_v2(conn)

            if current_version < 3:
                self._migrate_to_v3(conn)

            if current_version < 4:
                self._migrate_to_v4(conn)

            if current_version < 5:
                self._migrate_to_v5(conn)

            if current_version < 6:
                self._migrate_to_v6(conn)

            if current_version < 7:
                self._migrate_to_v7(conn)

            if current_version < 8:
                self._migrate_to_v8(conn)

            if current_version < 9:
                self._migrate_to_v9(conn)

            if current_version < 10:
                self._migrate_to_v10(conn)

            conn.commit()
        finally:
            conn.close()

    def _migrate_to_v2(self, conn):
        """Migrate from v1 to v2 schema."""
        cursor = conn.cursor()
        try:
            # Check if we already have trade_logs (already migrated)
            if self._table_exists(conn, 'trade_logs'):
                # Already migrated, just update version
                self._set_schema_version(conn, 2)
                return

            # Create new tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_logs (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,

                    -- Immutable Starting Parameters
                    starting_capital BIGINT NOT NULL,
                    risk_per_trade BIGINT,
                    max_position_size BIGINT,

                    -- Metadata
                    intent TEXT,
                    constraints TEXT,
                    regime_assumptions TEXT,
                    notes TEXT,

                    -- Status
                    is_active TINYINT DEFAULT 1,

                    created_at VARCHAR(32) DEFAULT (NOW()),
                    updated_at VARCHAR(32) DEFAULT (NOW())
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_events (
                    id VARCHAR(36) PRIMARY KEY,
                    trade_id VARCHAR(36) NOT NULL,

                    event_type VARCHAR(50) NOT NULL,
                    event_time VARCHAR(32) NOT NULL,

                    price BIGINT,
                    spot DECIMAL(10,4),
                    quantity_change INT,
                    notes TEXT,

                    created_at VARCHAR(32) DEFAULT (NOW()),

                    INDEX idx_events_trade (trade_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # Create fresh trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id VARCHAR(36) PRIMARY KEY,
                    log_id VARCHAR(36) NOT NULL,

                    symbol VARCHAR(20) NOT NULL,
                    underlying VARCHAR(50) NOT NULL,
                    strategy VARCHAR(50) NOT NULL,
                    side VARCHAR(20) NOT NULL,
                    strike DECIMAL(10,4) NOT NULL,
                    width INT,
                    dte INT,
                    quantity INT NOT NULL DEFAULT 1,

                    entry_time VARCHAR(32) NOT NULL,
                    entry_price BIGINT NOT NULL,
                    entry_spot DECIMAL(10,4),
                    entry_iv DECIMAL(10,4),

                    exit_time VARCHAR(32),
                    exit_price BIGINT,
                    exit_spot DECIMAL(10,4),

                    planned_risk BIGINT,
                    max_profit BIGINT,
                    max_loss BIGINT,

                    pnl BIGINT,
                    r_multiple DECIMAL(10,4),

                    status VARCHAR(20) DEFAULT 'open',

                    notes TEXT,
                    tags TEXT,
                    source VARCHAR(50) DEFAULT 'manual',
                    playbook_id VARCHAR(36),

                    created_at VARCHAR(32) DEFAULT (NOW()),
                    updated_at VARCHAR(32) DEFAULT (NOW()),

                    INDEX idx_trades_log_status (log_id, status),
                    INDEX idx_trades_entry_time (entry_time),
                    FOREIGN KEY (log_id) REFERENCES trade_logs(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            self._set_schema_version(conn, 2)
        finally:
            cursor.close()

    def _migrate_to_v3(self, conn):
        """Migrate to v3: Add symbols and settings tables."""
        cursor = conn.cursor()
        try:
            # Check if symbols table already exists
            if not self._table_exists(conn, 'symbols'):
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS symbols (
                        symbol VARCHAR(20) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        asset_type VARCHAR(50) NOT NULL,
                        multiplier INT NOT NULL,
                        enabled TINYINT DEFAULT 1,
                        is_default TINYINT DEFAULT 0,
                        created_at VARCHAR(32) DEFAULT (NOW())
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        `key` VARCHAR(100) NOT NULL,
                        value TEXT,
                        category VARCHAR(50) NOT NULL,
                        scope VARCHAR(50) DEFAULT 'global',
                        description TEXT,
                        updated_at VARCHAR(32) DEFAULT (NOW()),
                        PRIMARY KEY (`key`, scope),
                        INDEX idx_settings_category (category),
                        INDEX idx_settings_scope (scope)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # Insert default symbols
                now = datetime.utcnow().isoformat()
                for sym in self.DEFAULT_SYMBOLS:
                    cursor.execute("""
                        INSERT IGNORE INTO symbols (symbol, name, asset_type, multiplier, enabled, is_default, created_at)
                        VALUES (%s, %s, %s, %s, 1, 1, %s)
                    """, (sym['symbol'], sym['name'], sym['asset_type'], sym['multiplier'], now))

            self._set_schema_version(conn, 3)
        finally:
            cursor.close()

    def _migrate_to_v4(self, conn):
        """Migrate to v4: Add user_id to trade_logs for multi-user support."""
        cursor = conn.cursor()
        try:
            # Check if user_id column already exists
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'trade_logs'
                AND column_name = 'user_id'
            """)
            if cursor.fetchone()[0] > 0:
                # Already migrated
                self._set_schema_version(conn, 4)
                return

            # Add user_id column (nullable initially for existing data)
            cursor.execute("""
                ALTER TABLE trade_logs
                ADD COLUMN user_id INT NULL AFTER id,
                ADD INDEX idx_trade_logs_user (user_id)
            """)

            # Note: Foreign key to users table is not enforced here
            # since users table is managed by the auth system.
            # The constraint can be added later if needed:
            # ADD FOREIGN KEY (user_id) REFERENCES users(id)

            self._set_schema_version(conn, 4)
        finally:
            cursor.close()

    def _migrate_to_v5(self, conn):
        """Migrate to v5: Add journal tables (entries, retrospectives, trade refs, attachments)."""
        cursor = conn.cursor()
        try:
            # Create journal_entries table
            if not self._table_exists(conn, 'journal_entries'):
                cursor.execute("""
                    CREATE TABLE journal_entries (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,

                        entry_date DATE NOT NULL,
                        content LONGTEXT,

                        is_playbook_material TINYINT DEFAULT 0,

                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),

                        UNIQUE INDEX idx_entries_user_date (user_id, entry_date),
                        INDEX idx_entries_playbook (is_playbook_material)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create journal_retrospectives table
            if not self._table_exists(conn, 'journal_retrospectives'):
                cursor.execute("""
                    CREATE TABLE journal_retrospectives (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,

                        retro_type ENUM('weekly', 'monthly') NOT NULL,
                        period_start DATE NOT NULL,
                        period_end DATE NOT NULL,
                        content LONGTEXT,

                        is_playbook_material TINYINT DEFAULT 0,

                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),

                        UNIQUE INDEX idx_retro_user_period (user_id, retro_type, period_start),
                        INDEX idx_retro_playbook (is_playbook_material)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create journal_trade_refs table
            if not self._table_exists(conn, 'journal_trade_refs'):
                cursor.execute("""
                    CREATE TABLE journal_trade_refs (
                        id VARCHAR(36) PRIMARY KEY,

                        source_type ENUM('entry', 'retrospective') NOT NULL,
                        source_id VARCHAR(36) NOT NULL,
                        trade_id VARCHAR(36) NOT NULL,

                        note TEXT,

                        created_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_refs_source (source_type, source_id),
                        INDEX idx_refs_trade (trade_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create journal_attachments table
            if not self._table_exists(conn, 'journal_attachments'):
                cursor.execute("""
                    CREATE TABLE journal_attachments (
                        id VARCHAR(36) PRIMARY KEY,

                        source_type ENUM('entry', 'retrospective') NOT NULL,
                        source_id VARCHAR(36) NOT NULL,

                        filename VARCHAR(255) NOT NULL,
                        file_path VARCHAR(512) NOT NULL,
                        mime_type VARCHAR(100),
                        file_size INT,

                        created_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_attach_source (source_type, source_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create playbook_entries table
            if not self._table_exists(conn, 'playbook_entries'):
                cursor.execute("""
                    CREATE TABLE playbook_entries (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,

                        title VARCHAR(255) NOT NULL,
                        entry_type ENUM('pattern', 'rule', 'warning', 'filter', 'constraint') NOT NULL,
                        description TEXT,
                        status ENUM('draft', 'active', 'retired') DEFAULT 'draft',

                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_playbook_user (user_id),
                        INDEX idx_playbook_type (entry_type),
                        INDEX idx_playbook_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create playbook_source_refs table
            if not self._table_exists(conn, 'playbook_source_refs'):
                cursor.execute("""
                    CREATE TABLE playbook_source_refs (
                        id VARCHAR(36) PRIMARY KEY,
                        playbook_entry_id VARCHAR(36) NOT NULL,

                        source_type ENUM('entry', 'retrospective', 'trade') NOT NULL,
                        source_id VARCHAR(36) NOT NULL,
                        note TEXT,

                        created_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_pbref_entry (playbook_entry_id),
                        INDEX idx_pbref_source (source_type, source_id),
                        FOREIGN KEY (playbook_entry_id) REFERENCES playbook_entries(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 6)
        finally:
            cursor.close()

    def _migrate_to_v6(self, conn):
        """Migrate to v6: Add playbook tables if they don't exist (for DBs that ran v5 before playbook was added)."""
        cursor = conn.cursor()
        try:
            # Create playbook_entries table if it doesn't exist
            if not self._table_exists(conn, 'playbook_entries'):
                cursor.execute("""
                    CREATE TABLE playbook_entries (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,

                        title VARCHAR(255) NOT NULL,
                        entry_type ENUM('pattern', 'rule', 'warning', 'filter', 'constraint') NOT NULL,
                        description TEXT,
                        status ENUM('draft', 'active', 'retired') DEFAULT 'draft',

                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_playbook_user (user_id),
                        INDEX idx_playbook_type (entry_type),
                        INDEX idx_playbook_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create playbook_source_refs table if it doesn't exist
            if not self._table_exists(conn, 'playbook_source_refs'):
                cursor.execute("""
                    CREATE TABLE playbook_source_refs (
                        id VARCHAR(36) PRIMARY KEY,
                        playbook_entry_id VARCHAR(36) NOT NULL,

                        source_type ENUM('entry', 'retrospective', 'trade') NOT NULL,
                        source_id VARCHAR(36) NOT NULL,
                        note TEXT,

                        created_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_pbref_entry (playbook_entry_id),
                        INDEX idx_pbref_source (source_type, source_id),
                        FOREIGN KEY (playbook_entry_id) REFERENCES playbook_entries(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 6)
        finally:
            cursor.close()

    def _migrate_to_v7(self, conn):
        """Migrate to v7: Add tags table for trader vocabulary system."""
        cursor = conn.cursor()
        try:
            # Create tags table if it doesn't exist
            if not self._table_exists(conn, 'tags'):
                cursor.execute("""
                    CREATE TABLE tags (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        is_retired TINYINT DEFAULT 0,
                        is_example TINYINT DEFAULT 0,
                        usage_count INT DEFAULT 0,
                        last_used_at VARCHAR(32),
                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),

                        UNIQUE INDEX idx_tags_user_name (user_id, name),
                        INDEX idx_tags_user_retired (user_id, is_retired)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 7)
        finally:
            cursor.close()

    def _migrate_to_v8(self, conn):
        """Migrate to v8: Add tags column to journal_entries for tagging support."""
        cursor = conn.cursor()
        try:
            # Check if tags column already exists
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'journal_entries'
                AND column_name = 'tags'
            """)
            if cursor.fetchone()[0] == 0:
                # MySQL doesn't allow DEFAULT on TEXT columns
                cursor.execute("""
                    ALTER TABLE journal_entries
                    ADD COLUMN tags TEXT
                """)

            self._set_schema_version(conn, 8)
        finally:
            cursor.close()

    def _migrate_to_v9(self, conn):
        """Migrate to v9: Add alerts table for server-side alert persistence."""
        cursor = conn.cursor()
        try:
            if not self._table_exists(conn, 'alerts'):
                cursor.execute("""
                    CREATE TABLE alerts (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,

                        -- Core fields
                        type VARCHAR(50) NOT NULL,
                        intent_class VARCHAR(20) NOT NULL,
                        `condition` VARCHAR(20) NOT NULL,
                        target_value DECIMAL(12, 4),
                        behavior VARCHAR(20) DEFAULT 'once_only',
                        priority VARCHAR(20) DEFAULT 'medium',

                        -- Source reference
                        source_type VARCHAR(20) NOT NULL,
                        source_id VARCHAR(100) NOT NULL,

                        -- Strategy-specific (nullable)
                        strategy_id VARCHAR(36),
                        entry_debit DECIMAL(10, 2),

                        -- AI-specific (nullable)
                        min_profit_threshold DECIMAL(5, 2),
                        zone_low DECIMAL(12, 4),
                        zone_high DECIMAL(12, 4),
                        ai_confidence DECIMAL(3, 2),
                        ai_reasoning TEXT,

                        -- Trailing stop specific
                        high_water_mark DECIMAL(12, 4),

                        -- State
                        enabled TINYINT DEFAULT 1,
                        triggered TINYINT DEFAULT 0,
                        trigger_count INT DEFAULT 0,
                        triggered_at VARCHAR(32),

                        -- Display
                        label VARCHAR(100),
                        color VARCHAR(20) DEFAULT '#3b82f6',

                        -- Timestamps
                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_alerts_user (user_id),
                        INDEX idx_alerts_user_enabled (user_id, enabled),
                        INDEX idx_alerts_source (source_type, source_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 9)
        finally:
            cursor.close()

    def _migrate_to_v10(self, conn):
        """Migrate to v10: Add prompt alert tables for prompt-driven strategy alerts."""
        cursor = conn.cursor()
        try:
            # Create prompt_alerts table
            if not self._table_exists(conn, 'prompt_alerts'):
                cursor.execute("""
                    CREATE TABLE prompt_alerts (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,
                        strategy_id VARCHAR(36) NOT NULL,

                        -- Prompt content
                        prompt_text TEXT NOT NULL,
                        prompt_version INT DEFAULT 1,

                        -- AI-parsed semantic zones (JSON)
                        parsed_reference_logic TEXT,
                        parsed_deviation_logic TEXT,
                        parsed_evaluation_mode VARCHAR(20),
                        parsed_stage_thresholds TEXT,

                        -- User declarations
                        confidence_threshold ENUM('high', 'medium', 'low') DEFAULT 'medium',

                        -- Orchestration
                        orchestration_mode ENUM('parallel', 'overlapping', 'sequential') DEFAULT 'parallel',
                        orchestration_group_id VARCHAR(36),
                        sequence_order INT DEFAULT 0,
                        activates_after_alert_id VARCHAR(36),

                        -- State
                        lifecycle_state ENUM('active', 'dormant', 'accomplished') DEFAULT 'active',
                        current_stage ENUM('watching', 'update', 'warn', 'accomplished') DEFAULT 'watching',

                        -- Last evaluation
                        last_ai_confidence DECIMAL(3,2),
                        last_ai_reasoning TEXT,
                        last_evaluation_at VARCHAR(32),

                        -- Timestamps
                        created_at VARCHAR(32) DEFAULT (NOW()),
                        updated_at VARCHAR(32) DEFAULT (NOW()),
                        activated_at VARCHAR(32),
                        accomplished_at VARCHAR(32),

                        INDEX idx_prompt_alerts_user (user_id),
                        INDEX idx_prompt_alerts_strategy (strategy_id),
                        INDEX idx_prompt_alerts_lifecycle (lifecycle_state),
                        INDEX idx_prompt_alerts_group (orchestration_group_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create prompt_alert_versions table (silent versioning)
            if not self._table_exists(conn, 'prompt_alert_versions'):
                cursor.execute("""
                    CREATE TABLE prompt_alert_versions (
                        id VARCHAR(36) PRIMARY KEY,
                        prompt_alert_id VARCHAR(36) NOT NULL,
                        version INT NOT NULL,
                        prompt_text TEXT NOT NULL,
                        parsed_zones TEXT,
                        created_at VARCHAR(32) DEFAULT (NOW()),

                        UNIQUE INDEX idx_version_unique (prompt_alert_id, version),
                        INDEX idx_versions_alert (prompt_alert_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create reference_state_snapshots table (RiskGraph capture)
            if not self._table_exists(conn, 'reference_state_snapshots'):
                cursor.execute("""
                    CREATE TABLE reference_state_snapshots (
                        id VARCHAR(36) PRIMARY KEY,
                        prompt_alert_id VARCHAR(36) NOT NULL,

                        -- Greeks
                        delta DECIMAL(10,4),
                        gamma DECIMAL(10,6),
                        theta DECIMAL(10,4),

                        -- P&L
                        expiration_breakevens TEXT,
                        theoretical_breakevens TEXT,
                        max_profit DECIMAL(12,2),
                        max_loss DECIMAL(12,2),
                        pnl_at_spot DECIMAL(12,2),

                        -- Market
                        spot_price DECIMAL(12,4),
                        vix DECIMAL(6,2),
                        market_regime VARCHAR(20),

                        -- Strategy
                        dte INT,
                        debit DECIMAL(10,2),
                        strike DECIMAL(12,2),
                        width INT,
                        side VARCHAR(10),

                        captured_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_snapshots_alert (prompt_alert_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create prompt_alert_triggers table (history)
            if not self._table_exists(conn, 'prompt_alert_triggers'):
                cursor.execute("""
                    CREATE TABLE prompt_alert_triggers (
                        id VARCHAR(36) PRIMARY KEY,
                        prompt_alert_id VARCHAR(36) NOT NULL,
                        version_at_trigger INT,
                        stage VARCHAR(20),
                        ai_confidence DECIMAL(3,2),
                        ai_reasoning TEXT,
                        market_snapshot TEXT,
                        triggered_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_triggers_alert (prompt_alert_id),
                        INDEX idx_triggers_time (triggered_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 10)
        finally:
            cursor.close()

    # ==================== Trade Log CRUD ====================

    def create_log(self, log: TradeLog) -> TradeLog:
        """Create a new trade log."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = log.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO trade_logs ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return log
        finally:
            cursor.close()
            conn.close()

    def get_log(self, log_id: str, user_id: Optional[int] = None) -> Optional[TradeLog]:
        """Get a single trade log by ID, optionally filtered by user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if user_id is not None:
                cursor.execute(
                    "SELECT * FROM trade_logs WHERE id = %s AND user_id = %s AND is_active = 1",
                    (log_id, user_id)
                )
            else:
                cursor.execute(
                    "SELECT * FROM trade_logs WHERE id = %s AND is_active = 1",
                    (log_id,)
                )
            row = cursor.fetchone()

            if row:
                return TradeLog.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_logs(self, user_id: Optional[int] = None, include_inactive: bool = False) -> List[TradeLog]:
        """List trade logs, optionally filtered by user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM trade_logs WHERE 1=1"
            params = []

            if user_id is not None:
                query += " AND user_id = %s"
                params.append(user_id)

            if not include_inactive:
                query += " AND is_active = 1"

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [TradeLog.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_log(self, log_id: str, updates: Dict[str, Any], user_id: Optional[int] = None) -> Optional[TradeLog]:
        """Update a trade log (metadata only, not starting params)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'starting_capital', 'risk_per_trade', 'max_position_size', 'id', 'user_id', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_log(log_id, user_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())

            if user_id is not None:
                params = list(updates.values()) + [log_id, user_id]
                cursor.execute(
                    f"UPDATE trade_logs SET {set_clause} WHERE id = %s AND user_id = %s",
                    params
                )
            else:
                params = list(updates.values()) + [log_id]
                cursor.execute(
                    f"UPDATE trade_logs SET {set_clause} WHERE id = %s",
                    params
                )
            conn.commit()

            return self.get_log(log_id, user_id)
        finally:
            cursor.close()
            conn.close()

    def delete_log(self, log_id: str, user_id: Optional[int] = None) -> bool:
        """Soft delete a trade log."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if user_id is not None:
                cursor.execute(
                    "UPDATE trade_logs SET is_active = 0, updated_at = %s WHERE id = %s AND user_id = %s",
                    (datetime.utcnow().isoformat(), log_id, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE trade_logs SET is_active = 0, updated_at = %s WHERE id = %s",
                    (datetime.utcnow().isoformat(), log_id)
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def get_log_summary(self, log_id: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get a log with trade counts."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            log = self.get_log(log_id, user_id)
            if not log:
                return {}

            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status = 'closed' THEN pnl ELSE 0 END) as total_pnl
                FROM trades WHERE log_id = %s
            """, (log_id,))
            counts = cursor.fetchone()

            return {
                **log.to_api_dict(),
                'total_trades': counts[0] or 0,
                'open_trades': counts[1] or 0,
                'closed_trades': counts[2] or 0,
                'total_pnl': counts[3] or 0,
                'total_pnl_dollars': (counts[3] or 0) / 100
            }
        finally:
            cursor.close()
            conn.close()

    # ==================== Trade CRUD ====================

    def verify_log_ownership(self, log_id: str, user_id: int) -> bool:
        """Verify that a log belongs to a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM trade_logs WHERE id = %s AND user_id = %s AND is_active = 1",
                (log_id, user_id)
            )
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()
            conn.close()

    def create_trade(self, trade: Trade) -> Trade:
        """Create a new trade and auto-create OPEN event."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Insert trade
            data = trade.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO trades ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            # Create OPEN event
            event = TradeEvent(
                id=TradeEvent.new_id(),
                trade_id=trade.id,
                event_type='open',
                event_time=trade.entry_time,
                price=trade.entry_price,
                spot=trade.entry_spot
            )
            event_data = event.to_dict()
            event_columns = ', '.join(event_data.keys())
            event_placeholders = ', '.join(['%s'] * len(event_data))

            cursor.execute(
                f"INSERT INTO trade_events ({event_columns}) VALUES ({event_placeholders})",
                list(event_data.values())
            )

            conn.commit()
            return trade
        finally:
            cursor.close()
            conn.close()

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get a single trade by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM trades WHERE id = %s",
                (trade_id,)
            )
            row = cursor.fetchone()

            if row:
                return Trade.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_trade_with_events(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get a trade with all its events."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            trade = self.get_trade(trade_id)
            if not trade:
                return None

            cursor.execute(
                "SELECT * FROM trade_events WHERE trade_id = %s ORDER BY event_time ASC",
                (trade_id,)
            )
            events = cursor.fetchall()

            return {
                **trade.to_api_dict(),
                'events': [TradeEvent.from_dict(self._row_to_dict(cursor, e)).to_api_dict() for e in events]
            }
        finally:
            cursor.close()
            conn.close()

    def list_trades(
        self,
        log_id: str,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Trade]:
        """List trades in a log with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM trades WHERE log_id = %s"
            params: List[Any] = [log_id]

            if status and status != "all":
                query += " AND status = %s"
                params.append(status)

            if symbol:
                query += " AND symbol = %s"
                params.append(symbol)

            if strategy:
                query += " AND strategy = %s"
                params.append(strategy)

            if from_date:
                query += " AND entry_time >= %s"
                params.append(from_date)

            if to_date:
                query += " AND entry_time <= %s"
                params.append(to_date)

            query += " ORDER BY entry_time DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Trade.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_trade(self, trade_id: str, updates: Dict[str, Any]) -> Optional[Trade]:
        """Update a trade with the given fields."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            updates['updated_at'] = datetime.utcnow().isoformat()

            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
            params = list(updates.values()) + [trade_id]

            cursor.execute(
                f"UPDATE trades SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()

            return self.get_trade(trade_id)
        finally:
            cursor.close()
            conn.close()

    def add_adjustment(
        self,
        trade_id: str,
        price: int,
        quantity_change: int,
        spot: Optional[float] = None,
        notes: Optional[str] = None,
        event_time: Optional[str] = None
    ) -> Optional[TradeEvent]:
        """Add an adjustment event to a trade."""
        trade = self.get_trade(trade_id)
        if not trade or trade.status != 'open':
            return None

        if event_time is None:
            event_time = datetime.utcnow().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            event = TradeEvent(
                id=TradeEvent.new_id(),
                trade_id=trade_id,
                event_type='adjust',
                event_time=event_time,
                price=price,
                spot=spot,
                quantity_change=quantity_change,
                notes=notes
            )

            data = event.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO trade_events ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            # Update trade quantity
            new_quantity = trade.quantity + quantity_change
            cursor.execute(
                "UPDATE trades SET quantity = %s, updated_at = %s WHERE id = %s",
                (new_quantity, datetime.utcnow().isoformat(), trade_id)
            )

            conn.commit()
            return event
        finally:
            cursor.close()
            conn.close()

    def _get_multiplier(self, symbol: str) -> int:
        """Get the contract multiplier for a symbol."""
        # Matches the user's Excel lookup
        multipliers = {
            'SPX': 100,
            'NDX': 100,
            'XSP': 100,
            'SPY': 100,
            'ES': 50,
            'MES': 50,
            'NQ': 20,
            'MNQ': 20,
        }
        return multipliers.get(symbol.upper(), 100)  # Default to 100

    def close_trade(
        self,
        trade_id: str,
        exit_price: int,
        exit_spot: Optional[float] = None,
        exit_time: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[Trade]:
        """Close a trade and calculate P&L."""
        trade = self.get_trade(trade_id)
        if not trade or trade.status != 'open':
            return None

        if exit_time is None:
            exit_time = datetime.utcnow().isoformat()

        # Calculate P&L with symbol multiplier
        # Prices are stored in cents (per-share), so:
        # P&L = (exit - entry) * multiplier * quantity
        multiplier = self._get_multiplier(trade.symbol)
        pnl = (exit_price - trade.entry_price) * multiplier * trade.quantity
        r_multiple = None
        if trade.planned_risk and trade.planned_risk > 0:
            r_multiple = pnl / trade.planned_risk

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Update trade
            cursor.execute("""
                UPDATE trades SET
                    exit_time = %s, exit_price = %s, exit_spot = %s,
                    pnl = %s, r_multiple = %s, status = 'closed', updated_at = %s
                WHERE id = %s
            """, (exit_time, exit_price, exit_spot, pnl, r_multiple,
                  datetime.utcnow().isoformat(), trade_id))

            # Create CLOSE event
            event = TradeEvent(
                id=TradeEvent.new_id(),
                trade_id=trade_id,
                event_type='close',
                event_time=exit_time,
                price=exit_price,
                spot=exit_spot,
                notes=notes
            )
            data = event.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO trade_events ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            conn.commit()
            return self.get_trade(trade_id)
        finally:
            cursor.close()
            conn.close()

    def delete_trade(self, trade_id: str) -> bool:
        """Delete a trade and its events."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM trade_events WHERE trade_id = %s", (trade_id,))
            cursor.execute("DELETE FROM trades WHERE id = %s", (trade_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Events ====================

    def get_trade_events(self, trade_id: str) -> List[TradeEvent]:
        """Get all events for a trade."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM trade_events WHERE trade_id = %s ORDER BY event_time ASC",
                (trade_id,)
            )
            rows = cursor.fetchall()
            return [TradeEvent.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    # ==================== Symbols ====================

    def list_symbols(self, include_disabled: bool = False) -> List[Symbol]:
        """List all symbols (default + user-added)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM symbols"
            if not include_disabled:
                query += " WHERE enabled = 1"
            query += " ORDER BY asset_type, symbol"

            cursor.execute(query)
            rows = cursor.fetchall()
            return [Symbol.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_symbol(self, symbol: str) -> Optional[Symbol]:
        """Get a symbol by its ticker."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM symbols WHERE symbol = %s",
                (symbol.upper(),)
            )
            row = cursor.fetchone()
            if row:
                return Symbol.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_multiplier(self, symbol: str) -> int:
        """Get multiplier for a symbol, with fallback to defaults."""
        sym = self.get_symbol(symbol)
        if sym:
            return sym.multiplier
        # Fallback to hardcoded defaults
        return self._get_multiplier(symbol)

    def add_symbol(self, symbol: Symbol) -> Symbol:
        """Add a new user symbol."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            symbol.symbol = symbol.symbol.upper()
            symbol.is_default = False
            cursor.execute("""
                INSERT INTO symbols (symbol, name, asset_type, multiplier, enabled, is_default, created_at)
                VALUES (%s, %s, %s, %s, %s, 0, %s)
            """, (symbol.symbol, symbol.name, symbol.asset_type, symbol.multiplier,
                  1 if symbol.enabled else 0, symbol.created_at))
            conn.commit()
            return symbol
        finally:
            cursor.close()
            conn.close()

    def update_symbol(self, symbol: str, updates: Dict[str, Any]) -> Optional[Symbol]:
        """Update a symbol (only user-added symbols can be fully edited)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            symbol = symbol.upper()
            # Prevent editing symbol key
            updates.pop('symbol', None)
            updates.pop('is_default', None)

            if not updates:
                return self.get_symbol(symbol)

            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
            params = list(updates.values()) + [symbol]

            cursor.execute(
                f"UPDATE symbols SET {set_clause} WHERE symbol = %s",
                params
            )
            conn.commit()
            return self.get_symbol(symbol)
        finally:
            cursor.close()
            conn.close()

    def delete_symbol(self, symbol: str) -> bool:
        """Delete a user-added symbol (cannot delete default symbols)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM symbols WHERE symbol = %s AND is_default = 0",
                (symbol.upper(),)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Tags (Vocabulary System) ====================

    def list_tags(self, user_id: int, include_retired: bool = False) -> List[Tag]:
        """List all tags for a user, optionally including retired tags."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if include_retired:
                cursor.execute(
                    "SELECT * FROM tags WHERE user_id = %s ORDER BY last_used_at DESC, created_at DESC",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM tags WHERE user_id = %s AND is_retired = 0 ORDER BY last_used_at DESC, created_at DESC",
                    (user_id,)
                )
            rows = cursor.fetchall()
            return [Tag.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_tag(self, tag_id: str) -> Optional[Tag]:
        """Get a tag by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM tags WHERE id = %s", (tag_id,))
            row = cursor.fetchone()
            if row:
                return Tag.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_tag_by_name(self, user_id: int, name: str) -> Optional[Tag]:
        """Get a tag by user ID and name."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM tags WHERE user_id = %s AND name = %s",
                (user_id, name)
            )
            row = cursor.fetchone()
            if row:
                return Tag.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def create_tag(self, tag: Tag) -> Tag:
        """Create a new tag."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = tag.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO tags ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return tag
        finally:
            cursor.close()
            conn.close()

    def update_tag(self, tag_id: str, updates: Dict[str, Any]) -> Optional[Tag]:
        """Update a tag's editable fields (name, description)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Only allow updating name and description
            allowed = {'name', 'description'}
            updates = {k: v for k, v in updates.items() if k in allowed}

            if not updates:
                return self.get_tag(tag_id)

            updates['updated_at'] = datetime.utcnow().isoformat()
            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
            params = list(updates.values()) + [tag_id]

            cursor.execute(
                f"UPDATE tags SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()
            return self.get_tag(tag_id)
        finally:
            cursor.close()
            conn.close()

    def retire_tag(self, tag_id: str) -> Optional[Tag]:
        """Retire a tag (hide from suggestions but preserve on history)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE tags SET is_retired = 1, updated_at = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), tag_id)
            )
            conn.commit()
            return self.get_tag(tag_id)
        finally:
            cursor.close()
            conn.close()

    def restore_tag(self, tag_id: str) -> Optional[Tag]:
        """Restore a retired tag."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE tags SET is_retired = 0, updated_at = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), tag_id)
            )
            conn.commit()
            return self.get_tag(tag_id)
        finally:
            cursor.close()
            conn.close()

    def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag (only if usage_count is 0)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Only delete if tag has never been used
            cursor.execute(
                "DELETE FROM tags WHERE id = %s AND usage_count = 0",
                (tag_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def increment_tag_usage(self, tag_id: str) -> Optional[Tag]:
        """Increment usage count and update last_used_at when tag is applied."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "UPDATE tags SET usage_count = usage_count + 1, last_used_at = %s, updated_at = %s WHERE id = %s",
                (now, now, tag_id)
            )
            conn.commit()
            return self.get_tag(tag_id)
        finally:
            cursor.close()
            conn.close()

    def seed_example_tags(self, user_id: int) -> List[Tag]:
        """Seed default example tags for a new user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Check if user already has tags
            cursor.execute("SELECT COUNT(*) FROM tags WHERE user_id = %s", (user_id,))
            if cursor.fetchone()[0] > 0:
                # User already has tags, don't seed
                return []

            now = datetime.utcnow().isoformat()
            created_tags = []

            for tag_data in self.DEFAULT_TAGS:
                tag = Tag(
                    id=Tag.new_id(),
                    user_id=user_id,
                    name=tag_data['name'],
                    description=tag_data['description'],
                    is_example=True,
                    created_at=now,
                    updated_at=now
                )
                data = tag.to_dict()
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['%s'] * len(data))
                cursor.execute(
                    f"INSERT INTO tags ({columns}) VALUES ({placeholders})",
                    list(data.values())
                )
                created_tags.append(tag)

            conn.commit()
            return created_tags
        finally:
            cursor.close()
            conn.close()

    def count_tags(self, user_id: int) -> int:
        """Count total tags for a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM tags WHERE user_id = %s", (user_id,))
            return cursor.fetchone()[0]
        finally:
            cursor.close()
            conn.close()

    # ==================== Alerts ====================

    def list_alerts(
        self,
        user_id: int,
        enabled: Optional[bool] = None,
        alert_type: Optional[str] = None,
        source_id: Optional[str] = None,
        triggered: Optional[bool] = None
    ) -> List[Alert]:
        """List alerts for a user with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM alerts WHERE user_id = %s"
            params: List[Any] = [user_id]

            if enabled is not None:
                query += " AND enabled = %s"
                params.append(1 if enabled else 0)

            if alert_type:
                query += " AND type = %s"
                params.append(alert_type)

            if source_id:
                query += " AND source_id = %s"
                params.append(source_id)

            if triggered is not None:
                query += " AND triggered = %s"
                params.append(1 if triggered else 0)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Alert.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get a single alert by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM alerts WHERE id = %s", (alert_id,))
            row = cursor.fetchone()
            if row:
                return Alert.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def create_alert(self, alert: Alert) -> Alert:
        """Create a new alert."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = alert.to_dict()
            columns = ', '.join(f'`{k}`' if k == 'condition' else k for k in data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO alerts ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return alert
        finally:
            cursor.close()
            conn.close()

    def update_alert(self, alert_id: str, updates: Dict[str, Any]) -> Optional[Alert]:
        """Update an alert with the given fields."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'id', 'user_id', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_alert(alert_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            # Handle boolean conversions
            if 'enabled' in updates:
                updates['enabled'] = 1 if updates['enabled'] else 0
            if 'triggered' in updates:
                updates['triggered'] = 1 if updates['triggered'] else 0

            set_clause = ', '.join(
                f'`{k}` = %s' if k == 'condition' else f'{k} = %s'
                for k in updates.keys()
            )
            params = list(updates.values()) + [alert_id]

            cursor.execute(
                f"UPDATE alerts SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()
            return self.get_alert(alert_id)
        finally:
            cursor.close()
            conn.close()

    def delete_alert(self, alert_id: str) -> bool:
        """Delete an alert."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM alerts WHERE id = %s", (alert_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def reset_alert(self, alert_id: str) -> Optional[Alert]:
        """Reset an alert's trigger state (for repeat or manual reset)."""
        return self.update_alert(alert_id, {
            'triggered': False,
            'triggered_at': None
        })

    def get_all_enabled_alerts(self) -> List[Alert]:
        """Get all enabled alerts (for Copilot evaluation engine)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM alerts WHERE enabled = 1 ORDER BY priority DESC, created_at ASC"
            )
            rows = cursor.fetchall()
            return [Alert.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    # ==================== Prompt Alerts ====================

    def list_prompt_alerts(
        self,
        user_id: int,
        strategy_id: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        orchestration_group_id: Optional[str] = None
    ) -> List[PromptAlert]:
        """List prompt alerts for a user with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM prompt_alerts WHERE user_id = %s"
            params: List[Any] = [user_id]

            if strategy_id:
                query += " AND strategy_id = %s"
                params.append(strategy_id)

            if lifecycle_state:
                query += " AND lifecycle_state = %s"
                params.append(lifecycle_state)

            if orchestration_group_id:
                query += " AND orchestration_group_id = %s"
                params.append(orchestration_group_id)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [PromptAlert.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_prompt_alert(self, alert_id: str) -> Optional[PromptAlert]:
        """Get a single prompt alert by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM prompt_alerts WHERE id = %s", (alert_id,))
            row = cursor.fetchone()
            if row:
                return PromptAlert.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def create_prompt_alert(self, alert: PromptAlert) -> PromptAlert:
        """Create a new prompt alert."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = alert.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO prompt_alerts ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return alert
        finally:
            cursor.close()
            conn.close()

    def update_prompt_alert(self, alert_id: str, updates: Dict[str, Any]) -> Optional[PromptAlert]:
        """Update a prompt alert with the given fields."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'id', 'user_id', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_prompt_alert(alert_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
            params = list(updates.values()) + [alert_id]

            cursor.execute(
                f"UPDATE prompt_alerts SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()
            return self.get_prompt_alert(alert_id)
        finally:
            cursor.close()
            conn.close()

    def delete_prompt_alert(self, alert_id: str) -> bool:
        """Delete a prompt alert and its related records."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Delete related records first
            cursor.execute("DELETE FROM prompt_alert_triggers WHERE prompt_alert_id = %s", (alert_id,))
            cursor.execute("DELETE FROM reference_state_snapshots WHERE prompt_alert_id = %s", (alert_id,))
            cursor.execute("DELETE FROM prompt_alert_versions WHERE prompt_alert_id = %s", (alert_id,))
            cursor.execute("DELETE FROM prompt_alerts WHERE id = %s", (alert_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def get_active_prompt_alerts(self) -> List[PromptAlert]:
        """Get all active prompt alerts (for Copilot evaluation engine)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM prompt_alerts WHERE lifecycle_state = 'active' ORDER BY created_at ASC"
            )
            rows = cursor.fetchall()
            return [PromptAlert.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_prompt_alerts_for_strategy(self, strategy_id: str) -> List[PromptAlert]:
        """Get all prompt alerts for a specific strategy."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM prompt_alerts WHERE strategy_id = %s ORDER BY sequence_order ASC, created_at ASC",
                (strategy_id,)
            )
            rows = cursor.fetchall()
            return [PromptAlert.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def set_prompt_alerts_dormant_for_strategy(self, strategy_id: str) -> int:
        """Set all active prompt alerts for a strategy to dormant (when position closes)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE prompt_alerts SET lifecycle_state = 'dormant', updated_at = %s WHERE strategy_id = %s AND lifecycle_state = 'active'",
                (datetime.utcnow().isoformat(), strategy_id)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            cursor.close()
            conn.close()

    # ==================== Prompt Alert Versions ====================

    def create_prompt_alert_version(self, version: PromptAlertVersion) -> PromptAlertVersion:
        """Create a new prompt alert version record."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = version.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO prompt_alert_versions ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return version
        finally:
            cursor.close()
            conn.close()

    def get_prompt_alert_versions(self, prompt_alert_id: str) -> List[PromptAlertVersion]:
        """Get version history for a prompt alert."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM prompt_alert_versions WHERE prompt_alert_id = %s ORDER BY version DESC",
                (prompt_alert_id,)
            )
            rows = cursor.fetchall()
            return [PromptAlertVersion.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    # ==================== Reference State Snapshots ====================

    def create_reference_snapshot(self, snapshot: ReferenceStateSnapshot) -> ReferenceStateSnapshot:
        """Create a new reference state snapshot."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = snapshot.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO reference_state_snapshots ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return snapshot
        finally:
            cursor.close()
            conn.close()

    def get_reference_snapshot(self, prompt_alert_id: str) -> Optional[ReferenceStateSnapshot]:
        """Get the most recent reference snapshot for a prompt alert."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM reference_state_snapshots WHERE prompt_alert_id = %s ORDER BY captured_at DESC LIMIT 1",
                (prompt_alert_id,)
            )
            row = cursor.fetchone()
            if row:
                return ReferenceStateSnapshot.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all_reference_snapshots(self, prompt_alert_id: str) -> List[ReferenceStateSnapshot]:
        """Get all reference snapshots for a prompt alert (history)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM reference_state_snapshots WHERE prompt_alert_id = %s ORDER BY captured_at DESC",
                (prompt_alert_id,)
            )
            rows = cursor.fetchall()
            return [ReferenceStateSnapshot.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    # ==================== Prompt Alert Triggers ====================

    def create_prompt_alert_trigger(self, trigger: PromptAlertTrigger) -> PromptAlertTrigger:
        """Create a new prompt alert trigger record."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = trigger.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO prompt_alert_triggers ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return trigger
        finally:
            cursor.close()
            conn.close()

    def get_prompt_alert_triggers(self, prompt_alert_id: str) -> List[PromptAlertTrigger]:
        """Get trigger history for a prompt alert."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM prompt_alert_triggers WHERE prompt_alert_id = %s ORDER BY triggered_at DESC",
                (prompt_alert_id,)
            )
            rows = cursor.fetchall()
            return [PromptAlertTrigger.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    # ==================== Settings ====================

    def get_setting(self, key: str, scope: str = 'global') -> Optional[Setting]:
        """Get a setting by key and scope."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM settings WHERE `key` = %s AND scope = %s",
                (key, scope)
            )
            row = cursor.fetchone()
            if row:
                return Setting.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_settings_by_category(self, category: str, scope: str = 'global') -> List[Setting]:
        """Get all settings in a category."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM settings WHERE category = %s AND scope = %s",
                (category, scope)
            )
            rows = cursor.fetchall()
            return [Setting.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_all_settings(self, scope: str = 'global') -> Dict[str, Dict[str, Any]]:
        """Get all settings organized by category."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM settings WHERE scope = %s",
                (scope,)
            )
            rows = cursor.fetchall()

            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                s = Setting.from_dict(self._row_to_dict(cursor, row))
                if s.category not in result:
                    result[s.category] = {}
                result[s.category][s.key] = s.get_value()
            return result
        finally:
            cursor.close()
            conn.close()

    def set_setting(self, key: str, value: Any, category: str, scope: str = 'global',
                    description: Optional[str] = None) -> Setting:
        """Set a setting value (insert or update)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            value_json = json.dumps(value) if not isinstance(value, str) else value

            cursor.execute("""
                INSERT INTO settings (`key`, value, category, scope, description, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    value = VALUES(value),
                    category = VALUES(category),
                    description = COALESCE(VALUES(description), description),
                    updated_at = VALUES(updated_at)
            """, (key, value_json, category, scope, description, now))
            conn.commit()

            return Setting(key=key, value=value_json, category=category, scope=scope,
                          description=description, updated_at=now)
        finally:
            cursor.close()
            conn.close()

    def delete_setting(self, key: str, scope: str = 'global') -> bool:
        """Delete a setting."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM settings WHERE `key` = %s AND scope = %s",
                (key, scope)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def get_effective_setting(self, key: str, log_id: Optional[str] = None) -> Any:
        """Get effective setting value with per-log override support."""
        # First check for per-log setting
        if log_id:
            setting = self.get_setting(key, scope=log_id)
            if setting:
                return setting.get_value()

        # Fall back to global setting
        setting = self.get_setting(key, scope='global')
        if setting:
            return setting.get_value()

        return None

    # ==================== Analytics Helpers ====================

    def get_closed_trades_for_equity(
        self,
        log_id: str,
        user_id: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Trade]:
        """Get closed trades ordered by exit time for equity curve."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = """
                SELECT * FROM trades
                WHERE log_id = %s AND status = 'closed' AND exit_time IS NOT NULL
            """
            params: List[Any] = [log_id]

            if from_date:
                query += " AND exit_time >= %s"
                params.append(from_date)

            if to_date:
                query += " AND exit_time <= %s"
                params.append(to_date)

            query += " ORDER BY exit_time ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Trade.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_log_stats(self, log_id: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get basic statistics for a log."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            log = self.get_log(log_id, user_id)
            if not log:
                return {}

            # Total counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count
                FROM trades WHERE log_id = %s
            """, (log_id,))
            counts = cursor.fetchone()

            # P&L stats
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winners,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losers,
                    SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                    SUM(pnl) as total_pnl,
                    SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as gross_profit,
                    SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as gross_loss,
                    MAX(pnl) as largest_win,
                    MIN(pnl) as largest_loss,
                    AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                    AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                    AVG(planned_risk) as avg_risk,
                    AVG(r_multiple) as avg_r_multiple
                FROM trades
                WHERE log_id = %s AND status = 'closed'
            """, (log_id,))
            pnl_stats = cursor.fetchone()

            # Date range
            cursor.execute("""
                SELECT MIN(entry_time), MAX(COALESCE(exit_time, entry_time))
                FROM trades WHERE log_id = %s
            """, (log_id,))
            dates = cursor.fetchone()

            return {
                'log_id': log_id,
                'log_name': log.name,
                'starting_capital': log.starting_capital,
                'total_trades': counts[0] or 0,
                'open_trades': counts[1] or 0,
                'closed_trades': counts[2] or 0,
                'winners': pnl_stats[0] or 0,
                'losers': pnl_stats[1] or 0,
                'breakeven': pnl_stats[2] or 0,
                'total_pnl': pnl_stats[3] or 0,
                'gross_profit': pnl_stats[4] or 0,
                'gross_loss': pnl_stats[5] or 0,
                'largest_win': pnl_stats[6] or 0,
                'largest_loss': pnl_stats[7] or 0,
                'avg_win': pnl_stats[8] or 0,
                'avg_loss': pnl_stats[9] or 0,
                'avg_risk': pnl_stats[10] or 0,
                'avg_r_multiple': pnl_stats[11] or 0,
                'first_trade': dates[0],
                'last_trade': dates[1]
            }
        finally:
            cursor.close()
            conn.close()

    # ==================== Journal Entry CRUD ====================

    def create_entry(self, entry: JournalEntry) -> JournalEntry:
        """Create a new journal entry."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = entry.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO journal_entries ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return entry
        finally:
            cursor.close()
            conn.close()

    def get_entry(self, entry_id: str) -> Optional[JournalEntry]:
        """Get a single journal entry by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_entries WHERE id = %s",
                (entry_id,)
            )
            row = cursor.fetchone()
            if row:
                return JournalEntry.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_entry_by_date(self, user_id: int, date: str) -> Optional[JournalEntry]:
        """Get a journal entry by user and date."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_entries WHERE user_id = %s AND entry_date = %s",
                (user_id, date)
            )
            row = cursor.fetchone()
            if row:
                return JournalEntry.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_entries(
        self,
        user_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        playbook_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[JournalEntry]:
        """List journal entries for a user with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM journal_entries WHERE user_id = %s"
            params: List[Any] = [user_id]

            if from_date:
                query += " AND entry_date >= %s"
                params.append(from_date)

            if to_date:
                query += " AND entry_date <= %s"
                params.append(to_date)

            if playbook_only:
                query += " AND is_playbook_material = 1"

            query += " ORDER BY entry_date DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [JournalEntry.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_entry(self, entry_id: str, updates: Dict[str, Any]) -> Optional[JournalEntry]:
        """Update a journal entry."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'id', 'user_id', 'entry_date', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_entry(entry_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            # Handle boolean conversion
            if 'is_playbook_material' in updates:
                updates['is_playbook_material'] = 1 if updates['is_playbook_material'] else 0

            # Handle tags JSON conversion
            if 'tags' in updates:
                updates['tags'] = json.dumps(updates['tags']) if updates['tags'] else '[]'

            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
            params = list(updates.values()) + [entry_id]

            cursor.execute(
                f"UPDATE journal_entries SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()
            return self.get_entry(entry_id)
        finally:
            cursor.close()
            conn.close()

    def upsert_entry(self, entry: JournalEntry) -> JournalEntry:
        """Create or update entry by date (upsert)."""
        existing = self.get_entry_by_date(entry.user_id, entry.entry_date)
        if existing:
            updates = {
                'content': entry.content,
                'is_playbook_material': entry.is_playbook_material,
                'tags': entry.tags
            }
            return self.update_entry(existing.id, updates)
        return self.create_entry(entry)

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a journal entry and its attachments/trade refs."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Delete related records first
            cursor.execute(
                "DELETE FROM journal_trade_refs WHERE source_type = 'entry' AND source_id = %s",
                (entry_id,)
            )
            cursor.execute(
                "DELETE FROM journal_attachments WHERE source_type = 'entry' AND source_id = %s",
                (entry_id,)
            )
            cursor.execute("DELETE FROM journal_entries WHERE id = %s", (entry_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Journal Retrospective CRUD ====================

    def create_retrospective(self, retro: JournalRetrospective) -> JournalRetrospective:
        """Create a new retrospective."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = retro.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO journal_retrospectives ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return retro
        finally:
            cursor.close()
            conn.close()

    def get_retrospective(self, retro_id: str) -> Optional[JournalRetrospective]:
        """Get a single retrospective by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_retrospectives WHERE id = %s",
                (retro_id,)
            )
            row = cursor.fetchone()
            if row:
                return JournalRetrospective.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_retrospective_by_period(
        self,
        user_id: int,
        retro_type: str,
        period_start: str
    ) -> Optional[JournalRetrospective]:
        """Get a retrospective by user, type, and period start date."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_retrospectives WHERE user_id = %s AND retro_type = %s AND period_start = %s",
                (user_id, retro_type, period_start)
            )
            row = cursor.fetchone()
            if row:
                return JournalRetrospective.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_retrospectives(
        self,
        user_id: int,
        retro_type: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        playbook_only: bool = False
    ) -> List[JournalRetrospective]:
        """List retrospectives for a user with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM journal_retrospectives WHERE user_id = %s"
            params: List[Any] = [user_id]

            if retro_type:
                query += " AND retro_type = %s"
                params.append(retro_type)

            if from_date:
                query += " AND period_start >= %s"
                params.append(from_date)

            if to_date:
                query += " AND period_end <= %s"
                params.append(to_date)

            if playbook_only:
                query += " AND is_playbook_material = 1"

            query += " ORDER BY period_start DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [JournalRetrospective.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_retrospective(self, retro_id: str, updates: Dict[str, Any]) -> Optional[JournalRetrospective]:
        """Update a retrospective."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'id', 'user_id', 'retro_type', 'period_start', 'period_end', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_retrospective(retro_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            # Handle boolean conversion
            if 'is_playbook_material' in updates:
                updates['is_playbook_material'] = 1 if updates['is_playbook_material'] else 0

            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
            params = list(updates.values()) + [retro_id]

            cursor.execute(
                f"UPDATE journal_retrospectives SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()
            return self.get_retrospective(retro_id)
        finally:
            cursor.close()
            conn.close()

    def delete_retrospective(self, retro_id: str) -> bool:
        """Delete a retrospective and its attachments/trade refs."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Delete related records first
            cursor.execute(
                "DELETE FROM journal_trade_refs WHERE source_type = 'retrospective' AND source_id = %s",
                (retro_id,)
            )
            cursor.execute(
                "DELETE FROM journal_attachments WHERE source_type = 'retrospective' AND source_id = %s",
                (retro_id,)
            )
            cursor.execute("DELETE FROM journal_retrospectives WHERE id = %s", (retro_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Journal Trade References ====================

    def add_trade_ref(self, ref: JournalTradeRef) -> JournalTradeRef:
        """Add a trade reference to an entry or retrospective."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = ref.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO journal_trade_refs ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return ref
        finally:
            cursor.close()
            conn.close()

    def list_trade_refs(self, source_type: str, source_id: str) -> List[JournalTradeRef]:
        """List trade references for an entry or retrospective."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_trade_refs WHERE source_type = %s AND source_id = %s ORDER BY created_at",
                (source_type, source_id)
            )
            rows = cursor.fetchall()
            return [JournalTradeRef.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def list_trade_refs_by_trade(self, trade_id: str) -> List[JournalTradeRef]:
        """List all journal references to a specific trade."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_trade_refs WHERE trade_id = %s ORDER BY created_at",
                (trade_id,)
            )
            rows = cursor.fetchall()
            return [JournalTradeRef.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def delete_trade_ref(self, ref_id: str) -> bool:
        """Delete a trade reference."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM journal_trade_refs WHERE id = %s", (ref_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Journal Attachments ====================

    def create_attachment(self, attachment: JournalAttachment) -> JournalAttachment:
        """Create a new attachment record."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = attachment.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO journal_attachments ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return attachment
        finally:
            cursor.close()
            conn.close()

    def get_attachment(self, attachment_id: str) -> Optional[JournalAttachment]:
        """Get a single attachment by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_attachments WHERE id = %s",
                (attachment_id,)
            )
            row = cursor.fetchone()
            if row:
                return JournalAttachment.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_attachments(self, source_type: str, source_id: str) -> List[JournalAttachment]:
        """List attachments for an entry or retrospective."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM journal_attachments WHERE source_type = %s AND source_id = %s ORDER BY created_at",
                (source_type, source_id)
            )
            rows = cursor.fetchall()
            return [JournalAttachment.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment record (caller should delete file)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM journal_attachments WHERE id = %s", (attachment_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Calendar Queries (Temporal Gravity) ====================

    def get_calendar_month(self, user_id: int, year: int, month: int) -> Dict[str, Any]:
        """Get calendar view for a month showing which days have entries."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get entries for the month
            cursor.execute("""
                SELECT entry_date, is_playbook_material
                FROM journal_entries
                WHERE user_id = %s
                AND YEAR(entry_date) = %s AND MONTH(entry_date) = %s
                ORDER BY entry_date
            """, (user_id, year, month))
            entries = cursor.fetchall()

            days = {}
            for row in entries:
                date_str = row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
                days[date_str] = {
                    'has_entry': True,
                    'is_playbook_material': bool(row[1])
                }

            # Get retrospectives that overlap this month
            month_start = f"{year}-{month:02d}-01"
            if month == 12:
                month_end = f"{year + 1}-01-01"
            else:
                month_end = f"{year}-{month + 1:02d}-01"

            cursor.execute("""
                SELECT retro_type, period_start
                FROM journal_retrospectives
                WHERE user_id = %s
                AND period_start >= %s AND period_start < %s
            """, (user_id, month_start, month_end))
            retros = cursor.fetchall()

            weekly = []
            monthly_retro = None
            for row in retros:
                date_str = row[1].strftime('%Y-%m-%d') if hasattr(row[1], 'strftime') else str(row[1])
                if row[0] == 'weekly':
                    weekly.append(date_str)
                else:
                    monthly_retro = date_str

            return {
                'year': year,
                'month': month,
                'days': days,
                'retrospectives': {
                    'weekly': weekly if weekly else [],
                    'monthly': monthly_retro
                }
            }
        finally:
            cursor.close()
            conn.close()

    def get_calendar_week(self, user_id: int, week_start: str) -> Dict[str, Any]:
        """Get calendar view for a week showing which days have entries."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Calculate week end (7 days from start)
            from datetime import timedelta
            start_date = datetime.strptime(week_start, '%Y-%m-%d')
            end_date = start_date + timedelta(days=6)
            week_end = end_date.strftime('%Y-%m-%d')

            # Get entries for the week
            cursor.execute("""
                SELECT entry_date, is_playbook_material
                FROM journal_entries
                WHERE user_id = %s
                AND entry_date >= %s AND entry_date <= %s
                ORDER BY entry_date
            """, (user_id, week_start, week_end))
            entries = cursor.fetchall()

            days = {}
            for row in entries:
                date_str = row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
                days[date_str] = {
                    'has_entry': True,
                    'is_playbook_material': bool(row[1])
                }

            # Check if there's a weekly retrospective for this period
            cursor.execute("""
                SELECT id FROM journal_retrospectives
                WHERE user_id = %s AND retro_type = 'weekly' AND period_start = %s
            """, (user_id, week_start))
            retro = cursor.fetchone()

            return {
                'week_start': week_start,
                'week_end': week_end,
                'days': days,
                'has_retrospective': retro is not None
            }
        finally:
            cursor.close()
            conn.close()

    # ==================== Playbook CRUD ====================

    def create_playbook_entry(self, entry: PlaybookEntry) -> PlaybookEntry:
        """Create a new playbook entry."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = entry.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO playbook_entries ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return entry
        finally:
            cursor.close()
            conn.close()

    def get_playbook_entry(self, entry_id: str) -> Optional[PlaybookEntry]:
        """Get a playbook entry by ID."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM playbook_entries WHERE id = %s",
                (entry_id,)
            )
            row = cursor.fetchone()
            return PlaybookEntry.from_dict(row) if row else None
        finally:
            cursor.close()
            conn.close()

    def list_playbook_entries(
        self,
        user_id: int,
        entry_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PlaybookEntry]:
        """List playbook entries with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            query = "SELECT * FROM playbook_entries WHERE user_id = %s"
            params: List[Any] = [user_id]

            if entry_type:
                query += " AND entry_type = %s"
                params.append(entry_type)

            if status:
                query += " AND status = %s"
                params.append(status)

            if search:
                query += " AND (title LIKE %s OR description LIKE %s)"
                search_term = f"%{search}%"
                params.extend([search_term, search_term])

            query += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [PlaybookEntry.from_dict(row) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_playbook_entry(self, entry_id: str, updates: Dict[str, Any]) -> Optional[PlaybookEntry]:
        """Update a playbook entry."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            updates['updated_at'] = datetime.utcnow().isoformat()
            set_clause = ', '.join([f"{k} = %s" for k in updates.keys()])

            cursor.execute(
                f"UPDATE playbook_entries SET {set_clause} WHERE id = %s",
                list(updates.values()) + [entry_id]
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM playbook_entries WHERE id = %s", (entry_id,))
            row = cursor.fetchone()
            return PlaybookEntry.from_dict(row) if row else None
        finally:
            cursor.close()
            conn.close()

    def delete_playbook_entry(self, entry_id: str) -> bool:
        """Delete a playbook entry (source refs cascade)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM playbook_entries WHERE id = %s", (entry_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Playbook Source Refs ====================

    def create_playbook_source_ref(self, ref: PlaybookSourceRef) -> PlaybookSourceRef:
        """Create a source reference for a playbook entry."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = ref.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO playbook_source_refs ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return ref
        finally:
            cursor.close()
            conn.close()

    def list_playbook_source_refs(self, playbook_entry_id: str) -> List[PlaybookSourceRef]:
        """List source references for a playbook entry."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM playbook_source_refs WHERE playbook_entry_id = %s ORDER BY created_at",
                (playbook_entry_id,)
            )
            rows = cursor.fetchall()
            return [PlaybookSourceRef.from_dict(row) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def delete_playbook_source_ref(self, ref_id: str) -> bool:
        """Delete a source reference."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM playbook_source_refs WHERE id = %s", (ref_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def list_flagged_playbook_material(self, user_id: int) -> Dict[str, List[Dict]]:
        """List all journal entries and retrospectives flagged as playbook material."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            # Get flagged entries
            cursor.execute("""
                SELECT id, entry_date, content, created_at, updated_at
                FROM journal_entries
                WHERE user_id = %s AND is_playbook_material = 1
                ORDER BY entry_date DESC
            """, (user_id,))
            entries = cursor.fetchall()

            # Get flagged retrospectives
            cursor.execute("""
                SELECT id, retro_type, period_start, period_end, content, created_at, updated_at
                FROM journal_retrospectives
                WHERE user_id = %s AND is_playbook_material = 1
                ORDER BY period_start DESC
            """, (user_id,))
            retros = cursor.fetchall()

            # Convert dates to strings
            for e in entries:
                if hasattr(e.get('entry_date'), 'strftime'):
                    e['entry_date'] = e['entry_date'].strftime('%Y-%m-%d')

            for r in retros:
                if hasattr(r.get('period_start'), 'strftime'):
                    r['period_start'] = r['period_start'].strftime('%Y-%m-%d')
                if hasattr(r.get('period_end'), 'strftime'):
                    r['period_end'] = r['period_end'].strftime('%Y-%m-%d')

            return {
                'entries': entries,
                'retrospectives': retros
            }
        finally:
            cursor.close()
            conn.close()
