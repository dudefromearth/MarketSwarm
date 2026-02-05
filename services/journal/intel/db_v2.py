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
    PlaybookEntry, PlaybookSourceRef, Tag, Alert, Order, TradeCorrection,
    PromptAlert, PromptAlertVersion, ReferenceStateSnapshot, PromptAlertTrigger,
    TrackedIdea, SelectorParams,
    RiskGraphStrategy, RiskGraphStrategyVersion, RiskGraphTemplate,
    Position, Leg, Fill, PositionEvent, PositionJournalEntry,
    # ML Feedback Loop models
    MLDecision, PnLEvent, DailyPerformance, MLFeatureSnapshot,
    TrackedIdeaSnapshot, UserTradeAction, MLModel, MLExperiment
)


class JournalDBv2:
    """MySQL database manager for FOTW trade logs."""

    SCHEMA_VERSION = 18

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

            if current_version < 11:
                self._migrate_to_v11(conn)

            if current_version < 12:
                self._migrate_to_v12(conn)

            if current_version < 13:
                self._migrate_to_v13(conn)

            if current_version < 14:
                self._migrate_to_v14(conn)

            if current_version < 15:
                self._migrate_to_v15(conn)

            if current_version < 16:
                self._migrate_to_v16(conn)

            if current_version < 17:
                self._migrate_to_v17(conn)

            if current_version < 18:
                self._migrate_to_v18(conn)

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

    def _migrate_to_v11(self, conn):
        """Migrate to v11: Add butterfly entry detection and profit management fields to alerts."""
        cursor = conn.cursor()
        try:
            # Entry detection fields
            cursor.execute("""
                ALTER TABLE alerts
                ADD COLUMN entry_support_type VARCHAR(20),
                ADD COLUMN entry_support_level DECIMAL(10,4),
                ADD COLUMN entry_reversal_confirmed TINYINT DEFAULT 0,
                ADD COLUMN entry_target_strike DECIMAL(10,4),
                ADD COLUMN entry_target_width INT
            """)

            # Profit management fields
            cursor.execute("""
                ALTER TABLE alerts
                ADD COLUMN mgmt_activation_threshold DECIMAL(5,4) DEFAULT 0.75,
                ADD COLUMN mgmt_high_water_mark DECIMAL(12,4),
                ADD COLUMN mgmt_initial_dte INT,
                ADD COLUMN mgmt_initial_gamma DECIMAL(12,8),
                ADD COLUMN mgmt_risk_score DECIMAL(5,2),
                ADD COLUMN mgmt_recommendation VARCHAR(20),
                ADD COLUMN mgmt_last_assessment VARCHAR(32)
            """)

            self._set_schema_version(conn, 11)
        finally:
            cursor.close()

    def _migrate_to_v12(self, conn):
        """Migrate to v12: Add Trade Idea Tracking tables for feedback optimization loop."""
        cursor = conn.cursor()
        try:
            # Create tracked_ideas table - stores all settled trade ideas for analytics
            if not self._table_exists(conn, 'tracked_ideas'):
                cursor.execute("""
                    CREATE TABLE tracked_ideas (
                        id VARCHAR(64) PRIMARY KEY,

                        -- Entry Context
                        symbol VARCHAR(20) NOT NULL,
                        entry_rank INT NOT NULL,
                        entry_time VARCHAR(32) NOT NULL,
                        entry_ts BIGINT NOT NULL,
                        entry_spot DECIMAL(10,2) NOT NULL,
                        entry_vix DECIMAL(6,2) NOT NULL,
                        entry_regime VARCHAR(20) NOT NULL,

                        -- Trade Parameters
                        strategy VARCHAR(30) NOT NULL,
                        side VARCHAR(10) NOT NULL,
                        strike DECIMAL(10,2) NOT NULL,
                        width INT NOT NULL,
                        dte INT NOT NULL,
                        debit DECIMAL(10,2) NOT NULL,
                        max_profit_theoretical DECIMAL(10,2) NOT NULL,
                        r2r_predicted DECIMAL(6,2),
                        campaign VARCHAR(50),

                        -- Max Profit Tracking
                        max_pnl DECIMAL(10,2) NOT NULL,
                        max_pnl_time VARCHAR(32),
                        max_pnl_spot DECIMAL(10,2),
                        max_pnl_dte INT,

                        -- Settlement
                        settlement_time VARCHAR(32) NOT NULL,
                        settlement_spot DECIMAL(10,2) NOT NULL,
                        final_pnl DECIMAL(10,2) NOT NULL,
                        is_winner TINYINT NOT NULL,
                        pnl_captured_pct DECIMAL(6,2),
                        r2r_achieved DECIMAL(6,2),

                        -- Scoring Context (for feedback analysis)
                        score_total DECIMAL(8,4),
                        score_regime DECIMAL(8,4),
                        score_r2r DECIMAL(8,4),
                        score_convexity DECIMAL(8,4),
                        score_campaign DECIMAL(8,4),
                        score_decay DECIMAL(8,4),
                        score_edge DECIMAL(8,4),

                        -- Parameter Version (links to selector_params)
                        params_version INT,

                        -- Metadata
                        edge_cases TEXT,
                        created_at VARCHAR(32) DEFAULT (NOW()),

                        INDEX idx_tracked_entry_time (entry_ts),
                        INDEX idx_tracked_regime (entry_regime),
                        INDEX idx_tracked_strategy (strategy),
                        INDEX idx_tracked_rank (entry_rank),
                        INDEX idx_tracked_winner (is_winner),
                        INDEX idx_tracked_params (params_version)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create selector_params table - versioned scoring parameters
            if not self._table_exists(conn, 'selector_params'):
                cursor.execute("""
                    CREATE TABLE selector_params (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        version INT NOT NULL UNIQUE,

                        -- Status
                        status ENUM('draft', 'active', 'testing', 'retired') DEFAULT 'draft',
                        name VARCHAR(100),
                        description TEXT,

                        -- Scoring Weights (JSON for flexibility)
                        weights JSON NOT NULL,

                        -- Regime Thresholds
                        regime_thresholds JSON,

                        -- Performance Metrics (updated by feedback loop)
                        total_ideas INT DEFAULT 0,
                        win_count INT DEFAULT 0,
                        win_rate DECIMAL(5,2),
                        avg_pnl DECIMAL(10,2),
                        avg_capture_rate DECIMAL(5,2),

                        -- A/B Testing
                        ab_test_group VARCHAR(20),
                        ab_test_id VARCHAR(36),

                        -- Metadata
                        created_at VARCHAR(32) DEFAULT (NOW()),
                        activated_at VARCHAR(32),
                        retired_at VARCHAR(32),

                        INDEX idx_params_status (status),
                        INDEX idx_params_ab (ab_test_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # Insert initial baseline parameters (version 1)
                cursor.execute("""
                    INSERT INTO selector_params (version, status, name, description, weights, regime_thresholds)
                    VALUES (
                        1,
                        'active',
                        'Baseline v1',
                        'Initial scoring weights based on FOTW methodology',
                        JSON_OBJECT(
                            'regime', 0.25,
                            'r2r', 0.20,
                            'convexity', 0.20,
                            'campaign', 0.15,
                            'decay', 0.10,
                            'edge', 0.10
                        ),
                        JSON_OBJECT(
                            'chaos', 32,
                            'goldilocks_2_lower', 23,
                            'goldilocks_1_lower', 17,
                            'zombieland_upper', 17
                        )
                    )
                """)

            self._set_schema_version(conn, 12)
        finally:
            cursor.close()

    def _migrate_to_v13(self, conn):
        """Migrate to v13: Add time and GEX context fields to tracked_ideas."""
        cursor = conn.cursor()
        try:
            # Add time context columns
            try:
                cursor.execute("""
                    ALTER TABLE tracked_ideas
                    ADD COLUMN entry_hour DECIMAL(4,2) AFTER entry_regime,
                    ADD COLUMN entry_day_of_week TINYINT AFTER entry_hour
                """)
            except Exception:
                pass  # Columns may already exist

            # Add GEX context columns
            try:
                cursor.execute("""
                    ALTER TABLE tracked_ideas
                    ADD COLUMN entry_gex_flip DECIMAL(10,2) AFTER entry_day_of_week,
                    ADD COLUMN entry_gex_call_wall DECIMAL(10,2) AFTER entry_gex_flip,
                    ADD COLUMN entry_gex_put_wall DECIMAL(10,2) AFTER entry_gex_call_wall
                """)
            except Exception:
                pass  # Columns may already exist

            # Add index for time-based analysis
            try:
                cursor.execute("""
                    ALTER TABLE tracked_ideas
                    ADD INDEX idx_tracked_hour (entry_hour),
                    ADD INDEX idx_tracked_day (entry_day_of_week)
                """)
            except Exception:
                pass  # Indexes may already exist

            self._set_schema_version(conn, 13)
        finally:
            cursor.close()

    def _migrate_to_v14(self, conn):
        """Migrate to v14: Add leaderboard_scores table for gamified leaderboard feature."""
        cursor = conn.cursor()
        try:
            if not self._table_exists(conn, 'leaderboard_scores'):
                cursor.execute("""
                    CREATE TABLE leaderboard_scores (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        period_type ENUM('weekly', 'monthly', 'all_time') NOT NULL,
                        period_key VARCHAR(20) NOT NULL,

                        -- Activity Metrics
                        trades_logged INT DEFAULT 0,
                        journal_entries INT DEFAULT 0,
                        tags_used INT DEFAULT 0,

                        -- Performance Metrics
                        total_pnl BIGINT DEFAULT 0,
                        win_rate DECIMAL(5,2) DEFAULT 0,
                        avg_r_multiple DECIMAL(6,3) DEFAULT 0,
                        closed_trades INT DEFAULT 0,

                        -- Computed Scores (0-50 each, 0-100 total)
                        activity_score DECIMAL(10,2) DEFAULT 0,
                        performance_score DECIMAL(10,2) DEFAULT 0,
                        total_score DECIMAL(10,2) DEFAULT 0,
                        rank_position INT DEFAULT 0,

                        calculated_at DATETIME NOT NULL,

                        UNIQUE KEY uq_user_period (user_id, period_type, period_key),
                        INDEX idx_period_rank (period_type, period_key, rank_position),
                        INDEX idx_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 14)
        finally:
            cursor.close()

    def _migrate_to_v15(self, conn):
        """Migrate to v15: Add trade entry modes and order queue for simulated trading."""
        cursor = conn.cursor()
        try:
            # Add entry_mode column to trades table
            try:
                cursor.execute("""
                    ALTER TABLE trades
                    ADD COLUMN entry_mode ENUM('instant', 'freeform', 'simulated') DEFAULT 'instant'
                    AFTER status
                """)
            except Exception:
                pass  # Column may already exist

            # Add immutable_at timestamp for simulated trades (core fields locked after this)
            try:
                cursor.execute("""
                    ALTER TABLE trades
                    ADD COLUMN immutable_at DATETIME DEFAULT NULL
                    AFTER entry_mode
                """)
            except Exception:
                pass  # Column may already exist

            # Create trade_corrections table for auditable corrections to locked trades
            if not self._table_exists(conn, 'trade_corrections'):
                cursor.execute("""
                    CREATE TABLE trade_corrections (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        trade_id VARCHAR(36) NOT NULL,

                        -- What was corrected
                        field_name VARCHAR(50) NOT NULL,
                        original_value TEXT,
                        corrected_value TEXT NOT NULL,
                        correction_reason TEXT NOT NULL,

                        -- Audit trail
                        corrected_at DATETIME NOT NULL,
                        corrected_by INT,

                        INDEX idx_corrections_trade (trade_id),
                        FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create order_queue table for simulated orders
            if not self._table_exists(conn, 'order_queue'):
                cursor.execute("""
                    CREATE TABLE order_queue (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        trade_id VARCHAR(36) DEFAULT NULL,

                        -- Order details
                        order_type ENUM('entry', 'exit') NOT NULL,
                        symbol VARCHAR(20) NOT NULL,
                        direction ENUM('long', 'short') NOT NULL,

                        -- Limit order parameters
                        limit_price DECIMAL(10,2) NOT NULL,
                        quantity INT DEFAULT 1,

                        -- Trade parameters (for entry orders)
                        strategy VARCHAR(100) DEFAULT NULL,
                        stop_loss DECIMAL(10,2) DEFAULT NULL,
                        take_profit DECIMAL(10,2) DEFAULT NULL,
                        notes TEXT DEFAULT NULL,

                        -- Order lifecycle
                        status ENUM('pending', 'filled', 'cancelled', 'expired') DEFAULT 'pending',
                        created_at DATETIME NOT NULL,
                        expires_at DATETIME DEFAULT NULL,
                        filled_at DATETIME DEFAULT NULL,
                        filled_price DECIMAL(10,2) DEFAULT NULL,

                        INDEX idx_user_status (user_id, status),
                        INDEX idx_symbol_status (symbol, status),
                        FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 15)
        finally:
            cursor.close()

    def _migrate_to_v16(self, conn):
        """Migrate to v16: Add risk graph service tables for server-side strategy persistence."""
        cursor = conn.cursor()
        try:
            # Create risk_graph_strategies table - active strategies per user
            if not self._table_exists(conn, 'risk_graph_strategies'):
                cursor.execute("""
                    CREATE TABLE risk_graph_strategies (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,

                        -- Strategy geometry
                        symbol VARCHAR(20) NOT NULL DEFAULT 'SPX',
                        underlying VARCHAR(20) NOT NULL DEFAULT 'I:SPX',
                        strategy ENUM('single', 'vertical', 'butterfly') NOT NULL,
                        side ENUM('call', 'put') NOT NULL,
                        strike DECIMAL(10,2) NOT NULL,
                        width INT DEFAULT NULL,
                        dte INT NOT NULL,
                        expiration DATE NOT NULL,
                        debit DECIMAL(10,4) DEFAULT NULL,

                        -- Display state
                        visible BOOLEAN DEFAULT TRUE,
                        sort_order INT DEFAULT 0,
                        color VARCHAR(20) DEFAULT NULL,
                        label VARCHAR(100) DEFAULT NULL,

                        -- State
                        added_at BIGINT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                        INDEX idx_user_active (user_id, is_active)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create risk_graph_strategy_versions table - audit trail
            if not self._table_exists(conn, 'risk_graph_strategy_versions'):
                cursor.execute("""
                    CREATE TABLE risk_graph_strategy_versions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        strategy_id VARCHAR(36) NOT NULL,
                        version INT NOT NULL,
                        debit DECIMAL(10,4) DEFAULT NULL,
                        visible BOOLEAN DEFAULT TRUE,
                        label VARCHAR(100) DEFAULT NULL,
                        change_type ENUM('created', 'debit_updated', 'visibility_toggled', 'edited', 'deleted') NOT NULL,
                        change_reason VARCHAR(255) DEFAULT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                        FOREIGN KEY (strategy_id) REFERENCES risk_graph_strategies(id) ON DELETE CASCADE,
                        INDEX idx_strategy_version (strategy_id, version)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create risk_graph_templates table - saved/shareable templates
            if not self._table_exists(conn, 'risk_graph_templates'):
                cursor.execute("""
                    CREATE TABLE risk_graph_templates (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description TEXT DEFAULT NULL,

                        -- Template geometry (strike is relative to ATM)
                        symbol VARCHAR(20) NOT NULL DEFAULT 'SPX',
                        strategy ENUM('single', 'vertical', 'butterfly') NOT NULL,
                        side ENUM('call', 'put') NOT NULL,
                        strike_offset INT DEFAULT 0,
                        width INT DEFAULT NULL,
                        dte_target INT NOT NULL,
                        debit_estimate DECIMAL(10,4) DEFAULT NULL,

                        -- Sharing
                        is_public BOOLEAN DEFAULT FALSE,
                        share_code VARCHAR(20) DEFAULT NULL UNIQUE,
                        use_count INT DEFAULT 0,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_user_templates (user_id),
                        INDEX idx_share_code (share_code)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 16)
        finally:
            cursor.close()

    def _migrate_to_v17(self, conn):
        """Migrate to v17: Add normalized position/leg/fill tables for TradeLog service layer."""
        cursor = conn.cursor()
        try:
            # Create positions table - core aggregate for tracking trades
            if not self._table_exists(conn, 'positions'):
                cursor.execute("""
                    CREATE TABLE positions (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,
                        status ENUM('planned', 'open', 'closed') NOT NULL DEFAULT 'planned',
                        symbol VARCHAR(20) NOT NULL,
                        underlying VARCHAR(20) NOT NULL,
                        version INT NOT NULL DEFAULT 1,
                        opened_at DATETIME DEFAULT NULL,
                        closed_at DATETIME DEFAULT NULL,
                        tags JSON DEFAULT NULL,
                        campaign_id VARCHAR(36) DEFAULT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                        INDEX idx_user_status (user_id, status),
                        INDEX idx_campaign (campaign_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create legs table - individual option/stock/future legs
            if not self._table_exists(conn, 'legs'):
                cursor.execute("""
                    CREATE TABLE legs (
                        id VARCHAR(36) PRIMARY KEY,
                        position_id VARCHAR(36) NOT NULL,
                        instrument_type ENUM('option', 'stock', 'future') NOT NULL,
                        expiry DATE DEFAULT NULL,
                        strike DECIMAL(10,2) DEFAULT NULL,
                        `right` ENUM('call', 'put') DEFAULT NULL,
                        quantity INT NOT NULL,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                        FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
                        INDEX idx_position (position_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create fills table - price/quantity execution records
            if not self._table_exists(conn, 'fills'):
                cursor.execute("""
                    CREATE TABLE fills (
                        id VARCHAR(36) PRIMARY KEY,
                        leg_id VARCHAR(36) NOT NULL,
                        price DECIMAL(10,4) NOT NULL,
                        quantity INT NOT NULL,
                        occurred_at DATETIME NOT NULL,
                        recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                        FOREIGN KEY (leg_id) REFERENCES legs(id) ON DELETE CASCADE,
                        INDEX idx_leg (leg_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create idempotency_keys table - for mutation deduplication
            if not self._table_exists(conn, 'idempotency_keys'):
                cursor.execute("""
                    CREATE TABLE idempotency_keys (
                        id VARCHAR(100) PRIMARY KEY,
                        user_id INT NOT NULL,
                        response_status INT NOT NULL,
                        response_body JSON NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME NOT NULL,

                        INDEX idx_user_key (user_id, id),
                        INDEX idx_expires (expires_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create position_events table - SSE event log for replay
            if not self._table_exists(conn, 'position_events'):
                cursor.execute("""
                    CREATE TABLE position_events (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        event_id VARCHAR(36) NOT NULL UNIQUE,
                        event_seq BIGINT NOT NULL,
                        event_type VARCHAR(50) NOT NULL,
                        aggregate_type ENUM('position', 'order') NOT NULL,
                        aggregate_id VARCHAR(36) NOT NULL,
                        aggregate_version INT NOT NULL,
                        user_id INT NOT NULL,
                        payload JSON NOT NULL,
                        occurred_at DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                        INDEX idx_user_seq (user_id, event_seq),
                        INDEX idx_aggregate (aggregate_id, aggregate_version)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self._set_schema_version(conn, 17)
        finally:
            cursor.close()

    def _migrate_to_v18(self, conn):
        """Migrate to v18: Add ML Feedback Loop tables and position journal entries."""
        cursor = conn.cursor()
        try:
            # Create ml_decisions table - immutable decision records for reproducibility
            if not self._table_exists(conn, 'ml_decisions'):
                cursor.execute("""
                    CREATE TABLE ml_decisions (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        idea_id VARCHAR(36) NOT NULL,
                        decision_time DATETIME(3) NOT NULL,

                        -- Model identification (for exact reproducibility)
                        model_id INT DEFAULT NULL,
                        model_version INT DEFAULT NULL,
                        selector_params_version INT NOT NULL,
                        feature_snapshot_id BIGINT DEFAULT NULL,

                        -- Scores
                        original_score DECIMAL(6,2) NOT NULL,
                        ml_score DECIMAL(6,2) DEFAULT NULL,
                        final_score DECIMAL(6,2) NOT NULL,

                        -- Experiment tracking
                        experiment_id INT DEFAULT NULL,
                        experiment_arm ENUM('champion', 'challenger') DEFAULT NULL,

                        -- Action taken
                        action_taken ENUM('ranked', 'presented', 'traded', 'dismissed') DEFAULT 'ranked',

                        INDEX idx_idea (idea_id),
                        INDEX idx_decision_time (decision_time),
                        INDEX idx_model (model_id, model_version),
                        INDEX idx_experiment (experiment_id, experiment_arm)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create pnl_events table - append-only P&L tracking
            if not self._table_exists(conn, 'pnl_events'):
                cursor.execute("""
                    CREATE TABLE pnl_events (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        event_time DATETIME(3) NOT NULL,
                        idea_id VARCHAR(36) NOT NULL,
                        trade_id VARCHAR(36) DEFAULT NULL,
                        strategy_id VARCHAR(36) DEFAULT NULL,

                        -- P&L delta (not cumulative)
                        pnl_delta DECIMAL(12,2) NOT NULL,
                        fees DECIMAL(8,2) DEFAULT 0,
                        slippage DECIMAL(8,2) DEFAULT 0,

                        -- Context
                        underlying_price DECIMAL(10,2) NOT NULL,
                        event_type ENUM('mark', 'fill', 'settlement', 'adjustment') NOT NULL,

                        INDEX idx_idea_time (idea_id, event_time),
                        INDEX idx_trade (trade_id),
                        INDEX idx_event_time (event_time)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create daily_performance table - materialized from pnl_events
            if not self._table_exists(conn, 'daily_performance'):
                cursor.execute("""
                    CREATE TABLE daily_performance (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        date DATE NOT NULL UNIQUE,

                        -- P&L metrics
                        net_pnl DECIMAL(12,2) NOT NULL,
                        gross_pnl DECIMAL(12,2) NOT NULL,
                        total_fees DECIMAL(10,2) NOT NULL,

                        -- High water / drawdown
                        high_water_pnl DECIMAL(12,2) NOT NULL,
                        max_drawdown DECIMAL(12,2) NOT NULL,
                        drawdown_pct DECIMAL(6,4) DEFAULT NULL,

                        -- Volume metrics
                        trade_count INT NOT NULL,
                        win_count INT NOT NULL,
                        loss_count INT NOT NULL,

                        -- Model attribution
                        primary_model_id INT DEFAULT NULL,
                        ml_contribution_pct DECIMAL(6,4) DEFAULT NULL,

                        INDEX idx_date (date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create ml_feature_snapshots table - feature versioning for point-in-time correctness
            if not self._table_exists(conn, 'ml_feature_snapshots'):
                cursor.execute("""
                    CREATE TABLE ml_feature_snapshots (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        tracked_idea_id INT NOT NULL,
                        snapshot_time DATETIME(3) NOT NULL,

                        -- VERSIONING (critical for reproducibility)
                        feature_set_version VARCHAR(20) NOT NULL,
                        feature_extractor_version VARCHAR(20) NOT NULL,
                        gex_calc_version VARCHAR(20) DEFAULT NULL,
                        vix_regime_classifier_version VARCHAR(20) DEFAULT NULL,

                        -- Price Action Features
                        spot_price DECIMAL(10,2) NOT NULL,
                        spot_5m_return DECIMAL(8,6) DEFAULT NULL,
                        spot_15m_return DECIMAL(8,6) DEFAULT NULL,
                        spot_1h_return DECIMAL(8,6) DEFAULT NULL,
                        spot_1d_return DECIMAL(8,6) DEFAULT NULL,
                        intraday_high DECIMAL(10,2) DEFAULT NULL,
                        intraday_low DECIMAL(10,2) DEFAULT NULL,
                        range_position DECIMAL(6,4) DEFAULT NULL,

                        -- Volatility Features
                        vix_level DECIMAL(6,2) DEFAULT NULL,
                        vix_regime ENUM('chaos', 'goldilocks_1', 'goldilocks_2', 'zombieland') DEFAULT NULL,
                        vix_term_slope DECIMAL(8,4) DEFAULT NULL,
                        iv_rank_30d DECIMAL(6,4) DEFAULT NULL,
                        iv_percentile_30d DECIMAL(6,4) DEFAULT NULL,

                        -- GEX Structure Features
                        gex_total DECIMAL(15,2) DEFAULT NULL,
                        gex_call_wall DECIMAL(10,2) DEFAULT NULL,
                        gex_put_wall DECIMAL(10,2) DEFAULT NULL,
                        gex_gamma_flip DECIMAL(10,2) DEFAULT NULL,
                        spot_vs_call_wall DECIMAL(8,4) DEFAULT NULL,
                        spot_vs_put_wall DECIMAL(8,4) DEFAULT NULL,
                        spot_vs_gamma_flip DECIMAL(8,4) DEFAULT NULL,

                        -- Market Mode Features
                        market_mode VARCHAR(20) DEFAULT NULL,
                        bias_lfi DECIMAL(6,4) DEFAULT NULL,
                        bias_direction ENUM('bullish', 'bearish', 'neutral') DEFAULT NULL,

                        -- Time Features
                        minutes_since_open INT DEFAULT NULL,
                        day_of_week TINYINT DEFAULT NULL,
                        is_opex_week BOOLEAN DEFAULT FALSE,
                        days_to_monthly_opex INT DEFAULT NULL,

                        -- Cross-Asset Signals
                        es_futures_premium DECIMAL(6,4) DEFAULT NULL,
                        tnx_level DECIMAL(6,3) DEFAULT NULL,
                        dxy_level DECIMAL(6,2) DEFAULT NULL,

                        INDEX idx_idea_time (tracked_idea_id, snapshot_time),
                        INDEX idx_feature_version (feature_set_version)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create tracked_idea_snapshots table - event-based snapshots
            if not self._table_exists(conn, 'tracked_idea_snapshots'):
                cursor.execute("""
                    CREATE TABLE tracked_idea_snapshots (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        tracked_idea_id INT NOT NULL,
                        snapshot_time DATETIME(3) NOT NULL,

                        -- Trigger reason (controls when we snapshot)
                        trigger_type ENUM(
                            'fill',
                            'tier_boundary',
                            'stop_touch',
                            'target_touch',
                            'significant_move',
                            'periodic'
                        ) NOT NULL,

                        -- Position state
                        mark_price DECIMAL(10,4) NOT NULL,
                        underlying_price DECIMAL(10,2) NOT NULL,
                        unrealized_pnl DECIMAL(10,2) NOT NULL,
                        pnl_percent DECIMAL(8,4) NOT NULL,

                        -- Greeks snapshot
                        delta DECIMAL(8,4) DEFAULT NULL,
                        gamma DECIMAL(10,6) DEFAULT NULL,
                        theta DECIMAL(8,4) DEFAULT NULL,
                        vega DECIMAL(8,4) DEFAULT NULL,

                        -- Market context at snapshot
                        vix_level DECIMAL(6,2) DEFAULT NULL,

                        INDEX idx_idea_time (tracked_idea_id, snapshot_time),
                        INDEX idx_trigger (trigger_type)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create user_trade_actions table - behavior tracking
            if not self._table_exists(conn, 'user_trade_actions'):
                cursor.execute("""
                    CREATE TABLE user_trade_actions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        tracked_idea_id INT NOT NULL,
                        user_id INT NOT NULL,
                        action ENUM('viewed', 'dismissed', 'starred', 'traded', 'trade_closed') NOT NULL,
                        action_time DATETIME NOT NULL,

                        -- Trade details if action = 'traded'
                        fill_price DECIMAL(10,4) DEFAULT NULL,
                        fill_quantity INT DEFAULT NULL,
                        trade_id VARCHAR(36) DEFAULT NULL,

                        -- Exit details if action = 'trade_closed'
                        exit_price DECIMAL(10,4) DEFAULT NULL,
                        realized_pnl DECIMAL(10,2) DEFAULT NULL,

                        INDEX idx_idea_user (tracked_idea_id, user_id),
                        INDEX idx_user_time (user_id, action_time)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create ml_models table - model registry
            if not self._table_exists(conn, 'ml_models'):
                cursor.execute("""
                    CREATE TABLE ml_models (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        model_name VARCHAR(100) NOT NULL,
                        model_version INT NOT NULL,
                        model_type VARCHAR(50) NOT NULL,

                        -- Feature set version this model was trained on
                        feature_set_version VARCHAR(20) NOT NULL,

                        -- Model artifacts
                        model_blob LONGBLOB DEFAULT NULL,
                        feature_list JSON NOT NULL,
                        hyperparameters JSON NOT NULL,

                        -- Performance metrics
                        train_auc DECIMAL(6,4) DEFAULT NULL,
                        val_auc DECIMAL(6,4) DEFAULT NULL,
                        train_samples INT DEFAULT NULL,
                        val_samples INT DEFAULT NULL,

                        -- Calibration metrics
                        brier_tier_0 DECIMAL(6,4) DEFAULT NULL,
                        brier_tier_1 DECIMAL(6,4) DEFAULT NULL,
                        brier_tier_2 DECIMAL(6,4) DEFAULT NULL,
                        brier_tier_3 DECIMAL(6,4) DEFAULT NULL,

                        -- Top-k utility
                        top_10_avg_pnl DECIMAL(10,2) DEFAULT NULL,
                        top_20_avg_pnl DECIMAL(10,2) DEFAULT NULL,

                        -- Regime (optional - for regime-specific models)
                        regime VARCHAR(20) DEFAULT NULL,

                        -- Deployment state
                        status ENUM('training', 'validating', 'champion', 'challenger', 'retired') NOT NULL,
                        deployed_at DATETIME DEFAULT NULL,
                        retired_at DATETIME DEFAULT NULL,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                        UNIQUE KEY uk_name_version (model_name, model_version),
                        INDEX idx_status (status),
                        INDEX idx_regime (regime, status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create ml_experiments table - A/B experiment tracking
            if not self._table_exists(conn, 'ml_experiments'):
                cursor.execute("""
                    CREATE TABLE ml_experiments (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        experiment_name VARCHAR(100) NOT NULL,
                        description TEXT DEFAULT NULL,

                        champion_model_id INT NOT NULL,
                        challenger_model_id INT NOT NULL,
                        traffic_split DECIMAL(4,2) NOT NULL DEFAULT 0.10,

                        -- Stopping rules
                        max_duration_days INT DEFAULT 14,
                        min_samples_per_arm INT DEFAULT 100,
                        early_stop_threshold DECIMAL(8,6) DEFAULT 0.01,

                        -- Experiment state
                        status ENUM('running', 'concluded', 'aborted') NOT NULL,
                        started_at DATETIME NOT NULL,
                        ended_at DATETIME DEFAULT NULL,

                        -- Results
                        champion_samples INT DEFAULT 0,
                        challenger_samples INT DEFAULT 0,
                        champion_win_rate DECIMAL(6,4) DEFAULT NULL,
                        challenger_win_rate DECIMAL(6,4) DEFAULT NULL,
                        champion_avg_rar DECIMAL(8,4) DEFAULT NULL,
                        challenger_avg_rar DECIMAL(8,4) DEFAULT NULL,
                        p_value DECIMAL(8,6) DEFAULT NULL,
                        winner ENUM('champion', 'challenger', 'no_difference') DEFAULT NULL,

                        INDEX idx_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Create position_journal_entries table - TradeLog journaling tied to positions
            if not self._table_exists(conn, 'position_journal_entries'):
                cursor.execute("""
                    CREATE TABLE position_journal_entries (
                        id VARCHAR(36) PRIMARY KEY,
                        position_id VARCHAR(36) NOT NULL,
                        object_of_reflection TEXT NOT NULL,
                        bias_flags JSON DEFAULT NULL,
                        notes TEXT DEFAULT NULL,
                        phase ENUM('setup', 'entry', 'management', 'exit', 'review') NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                        FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
                        INDEX idx_position (position_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            # Add foreign keys after all tables exist (for ml_experiments)
            try:
                cursor.execute("""
                    ALTER TABLE ml_experiments
                    ADD CONSTRAINT fk_experiments_champion FOREIGN KEY (champion_model_id) REFERENCES ml_models(id),
                    ADD CONSTRAINT fk_experiments_challenger FOREIGN KEY (challenger_model_id) REFERENCES ml_models(id)
                """)
            except Exception:
                pass  # Foreign keys may already exist

            # Add outcome labels to tracked_ideas table
            try:
                cursor.execute("""
                    ALTER TABLE tracked_ideas
                    ADD COLUMN profit_tier TINYINT DEFAULT NULL AFTER is_winner,
                    ADD COLUMN risk_unit DECIMAL(10,2) DEFAULT NULL AFTER profit_tier,
                    ADD COLUMN max_favorable_excursion DECIMAL(8,4) DEFAULT NULL AFTER risk_unit,
                    ADD COLUMN max_adverse_excursion DECIMAL(8,4) DEFAULT NULL AFTER max_favorable_excursion,
                    ADD COLUMN time_to_max_pnl_pct DECIMAL(6,4) DEFAULT NULL AFTER max_adverse_excursion,
                    ADD COLUMN time_in_drawdown_pct DECIMAL(6,4) DEFAULT NULL AFTER time_to_max_pnl_pct,
                    ADD COLUMN hit_stop TINYINT DEFAULT NULL AFTER time_in_drawdown_pct,
                    ADD COLUMN hit_target TINYINT DEFAULT NULL AFTER hit_stop,
                    ADD COLUMN outperformed_median TINYINT DEFAULT NULL AFTER hit_target,
                    ADD COLUMN cohort_percentile DECIMAL(6,4) DEFAULT NULL AFTER outperformed_median
                """)
            except Exception:
                pass  # Columns may already exist

            self._set_schema_version(conn, 18)
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

    # ==================== Order Queue CRUD ====================

    def create_order(
        self,
        user_id: int,
        order_type: str,
        symbol: str,
        direction: str,
        limit_price: float,
        quantity: int = 1,
        trade_id: Optional[str] = None,
        strategy: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        notes: Optional[str] = None,
        expires_at: Optional[str] = None
    ) -> Optional[Order]:
        """Create a new order in the order queue."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow()
            cursor.execute("""
                INSERT INTO order_queue
                (user_id, trade_id, order_type, symbol, direction, limit_price, quantity,
                 strategy, stop_loss, take_profit, notes, status, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
            """, (
                user_id, trade_id, order_type, symbol, direction, limit_price, quantity,
                strategy, stop_loss, take_profit, notes, now, expires_at
            ))
            conn.commit()

            order_id = cursor.lastrowid
            return self.get_order(order_id)
        finally:
            cursor.close()
            conn.close()

    def get_order(self, order_id: int) -> Optional[Order]:
        """Get an order by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM order_queue WHERE id = %s", (order_id,))
            row = cursor.fetchone()
            if row:
                return Order.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_orders(
        self,
        user_id: int,
        status: Optional[str] = None,
        order_type: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Order]:
        """List orders for a user with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM order_queue WHERE user_id = %s"
            params = [user_id]

            if status:
                query += " AND status = %s"
                params.append(status)

            if order_type:
                query += " AND order_type = %s"
                params.append(order_type)

            if symbol:
                query += " AND symbol = %s"
                params.append(symbol)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Order.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def list_pending_orders(self, user_id: Optional[int] = None) -> List[Order]:
        """List all pending orders, optionally filtered by user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if user_id:
                cursor.execute(
                    "SELECT * FROM order_queue WHERE status = 'pending' AND user_id = %s ORDER BY created_at",
                    (user_id,)
                )
            else:
                cursor.execute("SELECT * FROM order_queue WHERE status = 'pending' ORDER BY created_at")
            rows = cursor.fetchall()
            return [Order.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_order_status(
        self,
        order_id: int,
        status: str,
        filled_price: Optional[float] = None
    ) -> Optional[Order]:
        """Update order status (fill, cancel, expire)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if status == 'filled':
                cursor.execute("""
                    UPDATE order_queue
                    SET status = %s, filled_at = %s, filled_price = %s
                    WHERE id = %s
                """, (status, datetime.utcnow(), filled_price, order_id))
            else:
                cursor.execute("""
                    UPDATE order_queue
                    SET status = %s
                    WHERE id = %s
                """, (status, order_id))
            conn.commit()
            return self.get_order(order_id)
        finally:
            cursor.close()
            conn.close()

    def cancel_order(self, order_id: int, user_id: int) -> bool:
        """Cancel an order (only if pending and owned by user)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE order_queue
                SET status = 'cancelled'
                WHERE id = %s AND user_id = %s AND status = 'pending'
            """, (order_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def expire_orders(self) -> int:
        """Mark expired orders as expired. Returns count of expired orders."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow()
            cursor.execute("""
                UPDATE order_queue
                SET status = 'expired'
                WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at < %s
            """, (now,))
            conn.commit()
            return cursor.rowcount
        finally:
            cursor.close()
            conn.close()

    def get_active_orders_summary(self, user_id: int) -> Dict[str, Any]:
        """Get summary of active orders for a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN order_type = 'entry' THEN 1 ELSE 0 END) as entry_count,
                    SUM(CASE WHEN order_type = 'exit' THEN 1 ELSE 0 END) as exit_count
                FROM order_queue
                WHERE user_id = %s AND status = 'pending'
            """, (user_id,))
            row = cursor.fetchone()
            return {
                'total': row[0] or 0,
                'pending_entries': row[1] or 0,
                'pending_exits': row[2] or 0
            }
        finally:
            cursor.close()
            conn.close()

    # ==================== Trade Corrections (Audit Trail) ====================

    def record_trade_correction(
        self,
        trade_id: str,
        field_name: str,
        original_value: str,
        corrected_value: str,
        correction_reason: str,
        user_id: Optional[int] = None
    ) -> TradeCorrection:
        """Record a correction to a locked simulated trade (audit trail)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow()
            cursor.execute("""
                INSERT INTO trade_corrections
                (trade_id, field_name, original_value, corrected_value, correction_reason,
                 corrected_at, corrected_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (trade_id, field_name, original_value, corrected_value, correction_reason,
                  now, user_id))
            conn.commit()

            correction_id = cursor.lastrowid
            return TradeCorrection(
                id=correction_id,
                trade_id=trade_id,
                field_name=field_name,
                original_value=original_value,
                corrected_value=corrected_value,
                correction_reason=correction_reason,
                corrected_at=now.isoformat(),
                corrected_by=user_id
            )
        finally:
            cursor.close()
            conn.close()

    def get_trade_corrections(self, trade_id: str) -> List[TradeCorrection]:
        """Get all corrections for a trade (audit log)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM trade_corrections
                WHERE trade_id = %s
                ORDER BY corrected_at ASC
            """, (trade_id,))
            rows = cursor.fetchall()
            return [TradeCorrection.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def lock_simulated_trade(self, trade_id: str) -> Optional[Trade]:
        """Lock a simulated trade by setting immutable_at timestamp."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute("""
                UPDATE trades
                SET immutable_at = %s, updated_at = %s
                WHERE id = %s AND entry_mode = 'simulated' AND immutable_at IS NULL
            """, (now, now, trade_id))
            conn.commit()
            return self.get_trade(trade_id)
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

    # ==================== Tracked Ideas CRUD ====================

    def create_tracked_idea(self, idea: TrackedIdea) -> TrackedIdea:
        """Create a new tracked idea record."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = idea.to_dict()
            # Convert edge_cases list to JSON if needed
            if isinstance(data.get('edge_cases'), list):
                data['edge_cases'] = json.dumps(data['edge_cases'])

            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO tracked_ideas ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return idea
        finally:
            cursor.close()
            conn.close()

    def get_tracked_idea(self, idea_id: str) -> Optional[TrackedIdea]:
        """Get a tracked idea by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM tracked_ideas WHERE id = %s", (idea_id,))
            row = cursor.fetchone()
            if row:
                return TrackedIdea.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_tracked_ideas(
        self,
        limit: int = 100,
        offset: int = 0,
        regime: Optional[str] = None,
        strategy: Optional[str] = None,
        rank: Optional[int] = None,
        is_winner: Optional[bool] = None,
        params_version: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TrackedIdea]:
        """List tracked ideas with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM tracked_ideas WHERE 1=1"
            params = []

            if regime:
                query += " AND entry_regime = %s"
                params.append(regime)
            if strategy:
                query += " AND strategy = %s"
                params.append(strategy)
            if rank is not None:
                query += " AND entry_rank = %s"
                params.append(rank)
            if is_winner is not None:
                query += " AND is_winner = %s"
                params.append(1 if is_winner else 0)
            if params_version is not None:
                query += " AND params_version = %s"
                params.append(params_version)
            if start_date:
                query += " AND entry_time >= %s"
                params.append(start_date)
            if end_date:
                query += " AND entry_time <= %s"
                params.append(end_date)

            query += " ORDER BY entry_ts DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [TrackedIdea.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_tracking_analytics(
        self,
        params_version: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get aggregated analytics for tracked ideas."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            # Base filter
            where_clause = "WHERE 1=1"
            params = []

            if params_version is not None:
                where_clause += " AND params_version = %s"
                params.append(params_version)
            if start_date:
                where_clause += " AND entry_time >= %s"
                params.append(start_date)
            if end_date:
                where_clause += " AND entry_time <= %s"
                params.append(end_date)

            # Overall stats
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_ideas,
                    SUM(is_winner) as win_count,
                    AVG(is_winner) * 100 as win_rate,
                    AVG(final_pnl) as avg_pnl,
                    AVG(max_pnl) as avg_max_pnl,
                    AVG(pnl_captured_pct) as avg_capture_rate
                FROM tracked_ideas
                {where_clause}
            """, params)
            overall = cursor.fetchone()

            # Stats by rank
            cursor.execute(f"""
                SELECT
                    entry_rank,
                    COUNT(*) as count,
                    SUM(is_winner) as wins,
                    AVG(is_winner) * 100 as win_rate,
                    AVG(final_pnl) as avg_pnl,
                    AVG(max_pnl) as avg_max_pnl,
                    AVG(pnl_captured_pct) as avg_capture_rate
                FROM tracked_ideas
                {where_clause}
                GROUP BY entry_rank
                ORDER BY entry_rank
            """, params)
            by_rank = cursor.fetchall()

            # Stats by regime
            cursor.execute(f"""
                SELECT
                    entry_regime,
                    COUNT(*) as count,
                    SUM(is_winner) as wins,
                    AVG(is_winner) * 100 as win_rate,
                    AVG(final_pnl) as avg_pnl,
                    AVG(pnl_captured_pct) as avg_capture_rate
                FROM tracked_ideas
                {where_clause}
                GROUP BY entry_regime
                ORDER BY count DESC
            """, params)
            by_regime = cursor.fetchall()

            # Stats by strategy
            cursor.execute(f"""
                SELECT
                    strategy,
                    side,
                    COUNT(*) as count,
                    SUM(is_winner) as wins,
                    AVG(is_winner) * 100 as win_rate,
                    AVG(final_pnl) as avg_pnl,
                    AVG(pnl_captured_pct) as avg_capture_rate
                FROM tracked_ideas
                {where_clause}
                GROUP BY strategy, side
                ORDER BY count DESC
            """, params)
            by_strategy = cursor.fetchall()

            # Optimal exit timing (when does max_pnl occur?)
            cursor.execute(f"""
                SELECT
                    entry_rank,
                    AVG(dte - max_pnl_dte) as avg_days_to_max,
                    AVG(max_pnl_dte) as avg_dte_at_max
                FROM tracked_ideas
                {where_clause} AND max_pnl_dte IS NOT NULL
                GROUP BY entry_rank
                ORDER BY entry_rank
            """, params)
            exit_timing = cursor.fetchall()

            return {
                'overall': overall,
                'byRank': by_rank,
                'byRegime': by_regime,
                'byStrategy': by_strategy,
                'exitTiming': exit_timing,
            }
        finally:
            cursor.close()
            conn.close()

    # ==================== Selector Params CRUD ====================

    def get_active_params(self) -> Optional[SelectorParams]:
        """Get the currently active selector parameters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM selector_params WHERE status = 'active' ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return SelectorParams.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_params_by_version(self, version: int) -> Optional[SelectorParams]:
        """Get selector parameters by version number."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM selector_params WHERE version = %s", (version,))
            row = cursor.fetchone()
            if row:
                return SelectorParams.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_params(self, include_retired: bool = False) -> List[SelectorParams]:
        """List all selector parameter versions."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if include_retired:
                cursor.execute("SELECT * FROM selector_params ORDER BY version DESC")
            else:
                cursor.execute(
                    "SELECT * FROM selector_params WHERE status != 'retired' ORDER BY version DESC"
                )
            rows = cursor.fetchall()
            return [SelectorParams.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def create_params(self, params: SelectorParams) -> SelectorParams:
        """Create a new parameter version."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get next version number
            cursor.execute("SELECT MAX(version) FROM selector_params")
            max_version = cursor.fetchone()[0] or 0
            params.version = max_version + 1

            data = params.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO selector_params ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            params.id = cursor.lastrowid
            conn.commit()
            return params
        finally:
            cursor.close()
            conn.close()

    def activate_params(self, version: int) -> bool:
        """Activate a parameter version (deactivates current active)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()

            # Deactivate current active
            cursor.execute(
                "UPDATE selector_params SET status = 'retired', retired_at = %s WHERE status = 'active'",
                (now,)
            )

            # Activate the requested version
            cursor.execute(
                "UPDATE selector_params SET status = 'active', activated_at = %s WHERE version = %s",
                (now, version)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def update_params_performance(
        self,
        version: int,
        total_ideas: int,
        win_count: int,
        avg_pnl: float,
        avg_capture_rate: float,
    ) -> bool:
        """Update performance metrics for a parameter version."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            win_rate = (win_count / total_ideas * 100) if total_ideas > 0 else 0

            cursor.execute("""
                UPDATE selector_params
                SET total_ideas = %s, win_count = %s, win_rate = %s, avg_pnl = %s, avg_capture_rate = %s
                WHERE version = %s
            """, (total_ideas, win_count, win_rate, avg_pnl, avg_capture_rate, version))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Leaderboard CRUD ====================

    def upsert_leaderboard_score(
        self,
        user_id: int,
        period_type: str,
        period_key: str,
        trades_logged: int,
        journal_entries: int,
        tags_used: int,
        total_pnl: int,
        win_rate: float,
        avg_r_multiple: float,
        closed_trades: int,
        activity_score: float,
        performance_score: float,
        total_score: float,
    ) -> bool:
        """Upsert a leaderboard score for a user/period."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()

            cursor.execute("""
                INSERT INTO leaderboard_scores
                    (user_id, period_type, period_key, trades_logged, journal_entries, tags_used,
                     total_pnl, win_rate, avg_r_multiple, closed_trades,
                     activity_score, performance_score, total_score, calculated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    trades_logged = VALUES(trades_logged),
                    journal_entries = VALUES(journal_entries),
                    tags_used = VALUES(tags_used),
                    total_pnl = VALUES(total_pnl),
                    win_rate = VALUES(win_rate),
                    avg_r_multiple = VALUES(avg_r_multiple),
                    closed_trades = VALUES(closed_trades),
                    activity_score = VALUES(activity_score),
                    performance_score = VALUES(performance_score),
                    total_score = VALUES(total_score),
                    calculated_at = VALUES(calculated_at)
            """, (
                user_id, period_type, period_key, trades_logged, journal_entries, tags_used,
                total_pnl, win_rate, avg_r_multiple, closed_trades,
                activity_score, performance_score, total_score, now
            ))
            conn.commit()
            return True
        finally:
            cursor.close()
            conn.close()

    def update_leaderboard_ranks(self, period_type: str, period_key: str) -> int:
        """Update rank positions for all users in a period. Returns count updated."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get all scores sorted by total_score descending
            cursor.execute("""
                SELECT id FROM leaderboard_scores
                WHERE period_type = %s AND period_key = %s
                ORDER BY total_score DESC, activity_score DESC, user_id ASC
            """, (period_type, period_key))

            rows = cursor.fetchall()
            count = 0

            for rank, (score_id,) in enumerate(rows, start=1):
                cursor.execute(
                    "UPDATE leaderboard_scores SET rank_position = %s WHERE id = %s",
                    (rank, score_id)
                )
                count += 1

            conn.commit()
            return count
        finally:
            cursor.close()
            conn.close()

    def get_leaderboard(
        self,
        period_type: str,
        period_key: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get leaderboard rankings for a period."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT
                    ls.user_id,
                    ls.rank_position,
                    ls.trades_logged,
                    ls.journal_entries,
                    ls.tags_used,
                    ls.total_pnl,
                    ls.win_rate,
                    ls.avg_r_multiple,
                    ls.closed_trades,
                    ls.activity_score,
                    ls.performance_score,
                    ls.total_score,
                    ls.calculated_at,
                    COALESCE(
                        CASE WHEN u.show_screen_name = 1 AND u.screen_name IS NOT NULL AND u.screen_name != '' THEN u.screen_name END,
                        u.display_name
                    ) as display_name
                FROM leaderboard_scores ls
                LEFT JOIN users u ON ls.user_id = u.id
                WHERE ls.period_type = %s AND ls.period_key = %s
                ORDER BY ls.rank_position ASC
                LIMIT %s OFFSET %s
            """, (period_type, period_key, limit, offset))

            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    'user_id': row[0],
                    'rank': row[1],
                    'trades_logged': row[2],
                    'journal_entries': row[3],
                    'tags_used': row[4],
                    'total_pnl': row[5],
                    'win_rate': float(row[6]) if row[6] else 0,
                    'avg_r_multiple': float(row[7]) if row[7] else 0,
                    'closed_trades': row[8],
                    'activity_score': float(row[9]) if row[9] else 0,
                    'performance_score': float(row[10]) if row[10] else 0,
                    'total_score': float(row[11]) if row[11] else 0,
                    'calculated_at': row[12],
                    'displayName': row[13],
                })

            return results
        finally:
            cursor.close()
            conn.close()

    def get_user_leaderboard_score(self, user_id: int, period_type: str, period_key: str) -> Optional[Dict[str, Any]]:
        """Get a specific user's leaderboard score for a period."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT
                    ls.user_id, ls.rank_position, ls.trades_logged, ls.journal_entries, ls.tags_used,
                    ls.total_pnl, ls.win_rate, ls.avg_r_multiple, ls.closed_trades,
                    ls.activity_score, ls.performance_score, ls.total_score, ls.calculated_at,
                    COALESCE(
                        CASE WHEN u.show_screen_name = 1 AND u.screen_name IS NOT NULL AND u.screen_name != '' THEN u.screen_name END,
                        u.display_name
                    ) as display_name
                FROM leaderboard_scores ls
                LEFT JOIN users u ON ls.user_id = u.id
                WHERE ls.user_id = %s AND ls.period_type = %s AND ls.period_key = %s
            """, (user_id, period_type, period_key))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'user_id': row[0],
                'rank': row[1],
                'trades_logged': row[2],
                'journal_entries': row[3],
                'tags_used': row[4],
                'total_pnl': row[5],
                'win_rate': float(row[6]) if row[6] else 0,
                'avg_r_multiple': float(row[7]) if row[7] else 0,
                'closed_trades': row[8],
                'activity_score': float(row[9]) if row[9] else 0,
                'performance_score': float(row[10]) if row[10] else 0,
                'total_score': float(row[11]) if row[11] else 0,
                'calculated_at': row[12],
                'displayName': row[13],
            }
        finally:
            cursor.close()
            conn.close()

    def get_leaderboard_participant_count(self, period_type: str, period_key: str) -> int:
        """Get total participant count for a period."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM leaderboard_scores
                WHERE period_type = %s AND period_key = %s
            """, (period_type, period_key))
            return cursor.fetchone()[0]
        finally:
            cursor.close()
            conn.close()

    def get_user_activity_metrics(self, user_id: int, start_date: str, end_date: str) -> Dict[str, int]:
        """Get activity metrics (trades, journal entries, tags) for a user in date range."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Count trades logged in period
            cursor.execute("""
                SELECT COUNT(*) FROM trades t
                JOIN trade_logs tl ON t.log_id = tl.id
                WHERE tl.user_id = %s
                AND t.entry_time >= %s AND t.entry_time < %s
            """, (user_id, start_date, end_date))
            trades_logged = cursor.fetchone()[0]

            # Count journal entries in period
            cursor.execute("""
                SELECT COUNT(*) FROM journal_entries
                WHERE user_id = %s
                AND entry_date >= %s AND entry_date < %s
            """, (user_id, start_date, end_date))
            journal_entries = cursor.fetchone()[0]

            # Count unique tags used on trades in period
            cursor.execute("""
                SELECT COUNT(DISTINCT tag_name) FROM (
                    SELECT JSON_UNQUOTE(JSON_EXTRACT(t.tags, CONCAT('$[', n.n, ']'))) AS tag_name
                    FROM trades t
                    JOIN trade_logs tl ON t.log_id = tl.id
                    JOIN (
                        SELECT 0 AS n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
                        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9
                    ) n
                    WHERE tl.user_id = %s
                    AND t.entry_time >= %s AND t.entry_time < %s
                    AND t.tags IS NOT NULL AND t.tags != '[]'
                    AND JSON_UNQUOTE(JSON_EXTRACT(t.tags, CONCAT('$[', n.n, ']'))) IS NOT NULL
                ) tag_list
            """, (user_id, start_date, end_date))
            tags_used = cursor.fetchone()[0]

            return {
                'trades_logged': trades_logged,
                'journal_entries': journal_entries,
                'tags_used': tags_used,
            }
        finally:
            cursor.close()
            conn.close()

    def get_user_performance_metrics(self, user_id: int, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get performance metrics for a user in date range."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get closed trades with P&L in period
            cursor.execute("""
                SELECT
                    COUNT(*) as closed_trades,
                    SUM(pnl) as total_pnl,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(r_multiple) as avg_r_multiple
                FROM trades t
                JOIN trade_logs tl ON t.log_id = tl.id
                WHERE tl.user_id = %s
                AND t.status = 'closed'
                AND t.exit_time >= %s AND t.exit_time < %s
            """, (user_id, start_date, end_date))

            row = cursor.fetchone()
            closed_trades = row[0] or 0
            total_pnl = row[1] or 0
            wins = row[2] or 0
            avg_r_multiple = float(row[3]) if row[3] else 0

            win_rate = (wins / closed_trades * 100) if closed_trades > 0 else 0

            return {
                'closed_trades': closed_trades,
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'avg_r_multiple': avg_r_multiple,
            }
        finally:
            cursor.close()
            conn.close()

    def get_all_user_ids_with_activity(self, start_date: str, end_date: str) -> List[int]:
        """Get all user IDs that have any activity in the date range."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get users with trades
            cursor.execute("""
                SELECT DISTINCT tl.user_id
                FROM trade_logs tl
                JOIN trades t ON t.log_id = tl.id
                WHERE tl.user_id IS NOT NULL
                AND (
                    (t.entry_time >= %s AND t.entry_time < %s)
                    OR (t.exit_time >= %s AND t.exit_time < %s)
                )
                UNION
                SELECT DISTINCT user_id
                FROM journal_entries
                WHERE user_id IS NOT NULL
                AND entry_date >= %s AND entry_date < %s
            """, (start_date, end_date, start_date, end_date, start_date, end_date))

            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    # ==================== Risk Graph Strategies ====================

    def list_risk_graph_strategies(
        self,
        user_id: int,
        include_inactive: bool = False
    ) -> List[RiskGraphStrategy]:
        """List risk graph strategies for a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM risk_graph_strategies WHERE user_id = %s"
            params: List[Any] = [user_id]

            if not include_inactive:
                query += " AND is_active = 1"

            query += " ORDER BY sort_order ASC, added_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [RiskGraphStrategy.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_risk_graph_strategy(self, strategy_id: str, user_id: Optional[int] = None) -> Optional[RiskGraphStrategy]:
        """Get a single risk graph strategy by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if user_id is not None:
                cursor.execute(
                    "SELECT * FROM risk_graph_strategies WHERE id = %s AND user_id = %s",
                    (strategy_id, user_id)
                )
            else:
                cursor.execute(
                    "SELECT * FROM risk_graph_strategies WHERE id = %s",
                    (strategy_id,)
                )
            row = cursor.fetchone()
            if row:
                return RiskGraphStrategy.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def create_risk_graph_strategy(self, strategy: RiskGraphStrategy) -> RiskGraphStrategy:
        """Create a new risk graph strategy."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = strategy.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO risk_graph_strategies ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            # Create initial version record
            version = RiskGraphStrategyVersion(
                strategy_id=strategy.id,
                version=1,
                debit=strategy.debit,
                visible=strategy.visible,
                label=strategy.label,
                change_type='created'
            )
            version_data = version.to_dict()
            v_columns = ', '.join(version_data.keys())
            v_placeholders = ', '.join(['%s'] * len(version_data))
            cursor.execute(
                f"INSERT INTO risk_graph_strategy_versions ({v_columns}) VALUES ({v_placeholders})",
                list(version_data.values())
            )

            conn.commit()
            return strategy
        finally:
            cursor.close()
            conn.close()

    def update_risk_graph_strategy(
        self,
        strategy_id: str,
        updates: Dict[str, Any],
        user_id: Optional[int] = None,
        change_reason: Optional[str] = None
    ) -> Optional[RiskGraphStrategy]:
        """Update a risk graph strategy with version tracking."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get current version
            if user_id is not None:
                cursor.execute(
                    "SELECT MAX(version) FROM risk_graph_strategy_versions WHERE strategy_id = %s",
                    (strategy_id,)
                )
            else:
                cursor.execute(
                    "SELECT MAX(version) FROM risk_graph_strategy_versions WHERE strategy_id = %s",
                    (strategy_id,)
                )
            row = cursor.fetchone()
            current_version = row[0] if row and row[0] else 0

            # Determine change type
            change_type = 'edited'
            if 'debit' in updates and len(updates) == 1:
                change_type = 'debit_updated'
            elif 'visible' in updates and len(updates) == 1:
                change_type = 'visibility_toggled'

            # Prevent updating immutable fields
            immutable = {'id', 'user_id', 'created_at', 'added_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_risk_graph_strategy(strategy_id, user_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            # Handle boolean conversions
            if 'visible' in updates:
                updates['visible'] = 1 if updates['visible'] else 0
            if 'is_active' in updates:
                updates['is_active'] = 1 if updates['is_active'] else 0

            set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
            if user_id is not None:
                params = list(updates.values()) + [strategy_id, user_id]
                cursor.execute(
                    f"UPDATE risk_graph_strategies SET {set_clause} WHERE id = %s AND user_id = %s",
                    params
                )
            else:
                params = list(updates.values()) + [strategy_id]
                cursor.execute(
                    f"UPDATE risk_graph_strategies SET {set_clause} WHERE id = %s",
                    params
                )

            # Create version record
            updated_strategy = self.get_risk_graph_strategy(strategy_id, user_id)
            if updated_strategy:
                version = RiskGraphStrategyVersion(
                    strategy_id=strategy_id,
                    version=current_version + 1,
                    debit=updated_strategy.debit,
                    visible=updated_strategy.visible,
                    label=updated_strategy.label,
                    change_type=change_type,
                    change_reason=change_reason
                )
                version_data = version.to_dict()
                v_columns = ', '.join(version_data.keys())
                v_placeholders = ', '.join(['%s'] * len(version_data))
                cursor.execute(
                    f"INSERT INTO risk_graph_strategy_versions ({v_columns}) VALUES ({v_placeholders})",
                    list(version_data.values())
                )

            conn.commit()
            return updated_strategy
        finally:
            cursor.close()
            conn.close()

    def delete_risk_graph_strategy(
        self,
        strategy_id: str,
        user_id: Optional[int] = None,
        hard_delete: bool = False
    ) -> bool:
        """Delete (soft or hard) a risk graph strategy."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if hard_delete:
                # Hard delete - cascade will remove versions
                if user_id is not None:
                    cursor.execute(
                        "DELETE FROM risk_graph_strategies WHERE id = %s AND user_id = %s",
                        (strategy_id, user_id)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM risk_graph_strategies WHERE id = %s",
                        (strategy_id,)
                    )
            else:
                # Soft delete
                now = datetime.utcnow().isoformat()
                if user_id is not None:
                    cursor.execute(
                        "UPDATE risk_graph_strategies SET is_active = 0, updated_at = %s WHERE id = %s AND user_id = %s",
                        (now, strategy_id, user_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE risk_graph_strategies SET is_active = 0, updated_at = %s WHERE id = %s",
                        (now, strategy_id)
                    )

                # Record deletion in version history
                cursor.execute(
                    "SELECT MAX(version) FROM risk_graph_strategy_versions WHERE strategy_id = %s",
                    (strategy_id,)
                )
                row = cursor.fetchone()
                current_version = row[0] if row and row[0] else 0

                version = RiskGraphStrategyVersion(
                    strategy_id=strategy_id,
                    version=current_version + 1,
                    change_type='deleted'
                )
                version_data = version.to_dict()
                v_columns = ', '.join(version_data.keys())
                v_placeholders = ', '.join(['%s'] * len(version_data))
                cursor.execute(
                    f"INSERT INTO risk_graph_strategy_versions ({v_columns}) VALUES ({v_placeholders})",
                    list(version_data.values())
                )

            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def get_risk_graph_strategy_versions(
        self,
        strategy_id: str
    ) -> List[RiskGraphStrategyVersion]:
        """Get version history for a strategy."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM risk_graph_strategy_versions WHERE strategy_id = %s ORDER BY version DESC",
                (strategy_id,)
            )
            rows = cursor.fetchall()
            return [RiskGraphStrategyVersion.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def reorder_risk_graph_strategies(
        self,
        user_id: int,
        strategy_order: List[str]
    ) -> bool:
        """Update sort order for multiple strategies."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            for idx, strategy_id in enumerate(strategy_order):
                cursor.execute(
                    "UPDATE risk_graph_strategies SET sort_order = %s WHERE id = %s AND user_id = %s",
                    (idx, strategy_id, user_id)
                )
            conn.commit()
            return True
        finally:
            cursor.close()
            conn.close()

    # ==================== Risk Graph Templates ====================

    def list_risk_graph_templates(
        self,
        user_id: int,
        include_public: bool = False
    ) -> List[RiskGraphTemplate]:
        """List risk graph templates for a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if include_public:
                cursor.execute(
                    "SELECT * FROM risk_graph_templates WHERE user_id = %s OR is_public = 1 ORDER BY created_at DESC",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM risk_graph_templates WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,)
                )
            rows = cursor.fetchall()
            return [RiskGraphTemplate.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def get_risk_graph_template(
        self,
        template_id: str,
        user_id: Optional[int] = None
    ) -> Optional[RiskGraphTemplate]:
        """Get a single template by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if user_id is not None:
                cursor.execute(
                    "SELECT * FROM risk_graph_templates WHERE id = %s AND (user_id = %s OR is_public = 1)",
                    (template_id, user_id)
                )
            else:
                cursor.execute(
                    "SELECT * FROM risk_graph_templates WHERE id = %s",
                    (template_id,)
                )
            row = cursor.fetchone()
            if row:
                return RiskGraphTemplate.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_risk_graph_template_by_share_code(
        self,
        share_code: str
    ) -> Optional[RiskGraphTemplate]:
        """Get a template by its share code."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM risk_graph_templates WHERE share_code = %s",
                (share_code,)
            )
            row = cursor.fetchone()
            if row:
                return RiskGraphTemplate.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def create_risk_graph_template(self, template: RiskGraphTemplate) -> RiskGraphTemplate:
        """Create a new risk graph template."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = template.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))

            cursor.execute(
                f"INSERT INTO risk_graph_templates ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return template
        finally:
            cursor.close()
            conn.close()

    def update_risk_graph_template(
        self,
        template_id: str,
        updates: Dict[str, Any],
        user_id: int
    ) -> Optional[RiskGraphTemplate]:
        """Update a template (only owner can update)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'id', 'user_id', 'created_at', 'use_count'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_risk_graph_template(template_id, user_id)

            # Handle boolean conversions
            if 'is_public' in updates:
                updates['is_public'] = 1 if updates['is_public'] else 0

            set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
            params = list(updates.values()) + [template_id, user_id]

            cursor.execute(
                f"UPDATE risk_graph_templates SET {set_clause} WHERE id = %s AND user_id = %s",
                params
            )
            conn.commit()
            return self.get_risk_graph_template(template_id, user_id)
        finally:
            cursor.close()
            conn.close()

    def delete_risk_graph_template(
        self,
        template_id: str,
        user_id: int
    ) -> bool:
        """Delete a template (only owner can delete)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM risk_graph_templates WHERE id = %s AND user_id = %s",
                (template_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def generate_template_share_code(
        self,
        template_id: str,
        user_id: int
    ) -> Optional[str]:
        """Generate a unique share code for a template."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Generate unique code
            share_code = RiskGraphTemplate.generate_share_code()

            cursor.execute(
                "UPDATE risk_graph_templates SET share_code = %s WHERE id = %s AND user_id = %s",
                (share_code, template_id, user_id)
            )
            conn.commit()

            if cursor.rowcount > 0:
                return share_code
            return None
        finally:
            cursor.close()
            conn.close()

    def increment_template_use_count(self, template_id: str) -> bool:
        """Increment the use count for a template."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE risk_graph_templates SET use_count = use_count + 1 WHERE id = %s",
                (template_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ==================== Position CRUD (TradeLog Service Layer) ====================

    def create_position(self, position: Position, legs: List[Leg]) -> Position:
        """Create a new position with legs."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Insert position
            pos_data = position.to_dict()
            columns = ', '.join(pos_data.keys())
            placeholders = ', '.join(['%s'] * len(pos_data))
            cursor.execute(
                f"INSERT INTO positions ({columns}) VALUES ({placeholders})",
                list(pos_data.values())
            )

            # Insert legs
            for leg in legs:
                leg_data = leg.to_dict()
                leg_cols = ', '.join(leg_data.keys())
                leg_ph = ', '.join(['%s'] * len(leg_data))
                cursor.execute(
                    f"INSERT INTO legs ({leg_cols}) VALUES ({leg_ph})",
                    list(leg_data.values())
                )

            conn.commit()

            # Return position with legs attached
            position.legs = legs
            return position
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def get_position(
        self,
        position_id: str,
        user_id: int,
        include_legs: bool = True,
        include_fills: bool = False
    ) -> Optional[Position]:
        """Get a position by ID with optional legs and fills."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM positions WHERE id = %s AND user_id = %s",
                (position_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                return None

            position = Position.from_dict(self._row_to_dict(cursor, row))

            if include_legs:
                cursor.execute(
                    "SELECT * FROM legs WHERE position_id = %s ORDER BY created_at",
                    (position_id,)
                )
                legs = [Leg.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
                position.legs = legs

                if include_fills and legs:
                    leg_ids = [l.id for l in legs]
                    placeholders = ', '.join(['%s'] * len(leg_ids))
                    cursor.execute(
                        f"SELECT * FROM fills WHERE leg_id IN ({placeholders}) ORDER BY occurred_at",
                        leg_ids
                    )
                    fills = [Fill.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
                    position.fills = fills

            return position
        finally:
            cursor.close()
            conn.close()

    def list_positions(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Position]:
        """List positions for a user, optionally filtered by status."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM positions WHERE user_id = %s"
            params = [user_id]

            if status:
                query += " AND status = %s"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            positions = [Position.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]

            # Fetch legs for all positions in one query
            if positions:
                pos_ids = [p.id for p in positions]
                placeholders = ', '.join(['%s'] * len(pos_ids))
                cursor.execute(
                    f"SELECT * FROM legs WHERE position_id IN ({placeholders}) ORDER BY created_at",
                    pos_ids
                )
                legs_by_pos = {}
                for row in cursor.fetchall():
                    leg = Leg.from_dict(self._row_to_dict(cursor, row))
                    if leg.position_id not in legs_by_pos:
                        legs_by_pos[leg.position_id] = []
                    legs_by_pos[leg.position_id].append(leg)

                for pos in positions:
                    pos.legs = legs_by_pos.get(pos.id, [])

            return positions
        finally:
            cursor.close()
            conn.close()

    def update_position(
        self,
        position_id: str,
        user_id: int,
        version: int,
        updates: dict
    ) -> Optional[Position]:
        """Update a position with optimistic locking (version check)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Check current version
            cursor.execute(
                "SELECT version FROM positions WHERE id = %s AND user_id = %s",
                (position_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            current_version = row[0]

            if current_version != version:
                # Version mismatch - raise conflict error
                raise VersionConflictError(current_version)

            # Build update query
            allowed_fields = ['status', 'tags', 'campaign_id', 'opened_at', 'closed_at']
            set_clauses = []
            params = []

            for field in allowed_fields:
                if field in updates:
                    value = updates[field]
                    if field == 'tags' and value is not None:
                        value = json.dumps(value)
                    set_clauses.append(f"{field} = %s")
                    params.append(value)

            if not set_clauses:
                return self.get_position(position_id, user_id)

            # Increment version
            set_clauses.append("version = version + 1")
            set_clauses.append("updated_at = NOW()")

            params.extend([position_id, user_id, version])

            cursor.execute(
                f"UPDATE positions SET {', '.join(set_clauses)} WHERE id = %s AND user_id = %s AND version = %s",
                params
            )

            if cursor.rowcount == 0:
                # Race condition - version changed between check and update
                cursor.execute(
                    "SELECT version FROM positions WHERE id = %s AND user_id = %s",
                    (position_id, user_id)
                )
                row = cursor.fetchone()
                if row:
                    raise VersionConflictError(row[0])
                return None

            conn.commit()
            return self.get_position(position_id, user_id)
        except VersionConflictError:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def record_fill(self, fill: Fill) -> Fill:
        """Record a fill for a leg."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            fill_data = fill.to_dict()
            columns = ', '.join(fill_data.keys())
            placeholders = ', '.join(['%s'] * len(fill_data))
            cursor.execute(
                f"INSERT INTO fills ({columns}) VALUES ({placeholders})",
                list(fill_data.values())
            )
            conn.commit()
            return fill
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def close_position(
        self,
        position_id: str,
        user_id: int,
        version: int
    ) -> Optional[Position]:
        """Close a position with optimistic locking."""
        return self.update_position(
            position_id,
            user_id,
            version,
            {
                'status': 'closed',
                'closed_at': datetime.utcnow().isoformat()
            }
        )

    def get_position_snapshot(
        self,
        position_id: str,
        user_id: int
    ) -> Optional[dict]:
        """Get a complete position snapshot for RiskGraph integration."""
        position = self.get_position(position_id, user_id, include_legs=True, include_fills=True)
        if not position:
            return None

        # Compute derived metadata
        legs = position.legs or []
        fills = position.fills or []

        # Derive strategy type
        if len(legs) == 1:
            derived_strategy = 'single'
        elif len(legs) == 2:
            derived_strategy = 'vertical'
        elif len(legs) == 3:
            derived_strategy = 'butterfly'
        else:
            derived_strategy = 'custom'

        # Compute net debit (sum of fill price * quantity)
        net_debit = sum(f.price * f.quantity for f in fills)

        # Compute DTE from first leg's expiry
        dte = None
        if legs and legs[0].expiry:
            try:
                expiry_date = datetime.strptime(legs[0].expiry, '%Y-%m-%d').date()
                dte = (expiry_date - datetime.utcnow().date()).days
            except (ValueError, TypeError):
                pass

        return {
            'positionId': position.id,
            'version': position.version,
            'status': position.status,
            'symbol': position.symbol,
            'underlying': position.underlying,
            'legs': [leg.to_api_dict() for leg in legs],
            'fills': [fill.to_api_dict() for fill in fills],
            'metadata': {
                'derivedStrategy': derived_strategy,
                'netDebit': net_debit,
                'dte': dte,
                'maxProfit': None,  # Computed by RiskGraph
                'maxLoss': None,  # Computed by RiskGraph
            }
        }

    # ==================== Position Events (SSE Event Log) ====================

    def record_position_event(self, event: PositionEvent) -> PositionEvent:
        """Record a position event for SSE replay."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Get next event_seq for this user
            cursor.execute(
                "SELECT COALESCE(MAX(event_seq), 0) + 1 FROM position_events WHERE user_id = %s",
                (event.user_id,)
            )
            event.event_seq = cursor.fetchone()[0]

            event_data = event.to_dict()
            columns = ', '.join(event_data.keys())
            placeholders = ', '.join(['%s'] * len(event_data))
            cursor.execute(
                f"INSERT INTO position_events ({columns}) VALUES ({placeholders})",
                list(event_data.values())
            )
            conn.commit()
            return event
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def get_position_events_since(
        self,
        user_id: int,
        last_seq: int = 0,
        limit: int = 100
    ) -> List[PositionEvent]:
        """Get position events since a given sequence number for replay."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM position_events WHERE user_id = %s AND event_seq > %s ORDER BY event_seq LIMIT %s",
                (user_id, last_seq, limit)
            )
            return [PositionEvent.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    # ==================== Idempotency Keys ====================

    def check_idempotency_key(
        self,
        key: str,
        user_id: int
    ) -> Optional[dict]:
        """Check if an idempotency key exists and return cached response."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT response_status, response_body FROM idempotency_keys WHERE id = %s AND user_id = %s AND expires_at > NOW()",
                (key, user_id)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'status': row[0],
                    'body': json.loads(row[1]) if row[1] else None
                }
            return None
        finally:
            cursor.close()
            conn.close()

    def store_idempotency_key(
        self,
        key: str,
        user_id: int,
        status: int,
        body: dict,
        ttl_hours: int = 24
    ) -> None:
        """Store an idempotency key with response."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO idempotency_keys (id, user_id, response_status, response_body, expires_at)
                VALUES (%s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))
                ON DUPLICATE KEY UPDATE
                    response_status = VALUES(response_status),
                    response_body = VALUES(response_body),
                    expires_at = VALUES(expires_at)
                """,
                (key, user_id, status, json.dumps(body), ttl_hours)
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def cleanup_expired_idempotency_keys(self) -> int:
        """Clean up expired idempotency keys. Returns count of deleted keys."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM idempotency_keys WHERE expires_at < NOW()")
            conn.commit()
            return cursor.rowcount
        finally:
            cursor.close()
            conn.close()

    # ==================== ML Feedback Loop CRUD ====================

    def create_ml_decision(self, decision: MLDecision) -> MLDecision:
        """Create an ML decision record."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = decision.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            cursor.execute(
                f"INSERT INTO ml_decisions ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            decision.id = cursor.lastrowid
            conn.commit()
            return decision
        finally:
            cursor.close()
            conn.close()

    def get_ml_decision(self, decision_id: int) -> Optional[MLDecision]:
        """Get an ML decision by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM ml_decisions WHERE id = %s", (decision_id,))
            row = cursor.fetchone()
            if row:
                return MLDecision.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_ml_decisions(
        self,
        idea_id: Optional[str] = None,
        model_id: Optional[int] = None,
        experiment_id: Optional[int] = None,
        limit: int = 100
    ) -> List[MLDecision]:
        """List ML decisions with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM ml_decisions WHERE 1=1"
            params = []

            if idea_id:
                query += " AND idea_id = %s"
                params.append(idea_id)
            if model_id:
                query += " AND model_id = %s"
                params.append(model_id)
            if experiment_id:
                query += " AND experiment_id = %s"
                params.append(experiment_id)

            query += " ORDER BY decision_time DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [MLDecision.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def update_ml_decision_action(self, decision_id: int, action: str) -> Optional[MLDecision]:
        """Update the action_taken for a decision (only valid progressions)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Validate progression
            valid_progressions = {
                'ranked': ('presented', 'dismissed'),
                'presented': ('traded', 'dismissed'),
            }

            cursor.execute("SELECT action_taken FROM ml_decisions WHERE id = %s", (decision_id,))
            row = cursor.fetchone()
            if not row:
                return None

            current = row[0]
            if action not in valid_progressions.get(current, ()):
                return None

            cursor.execute(
                "UPDATE ml_decisions SET action_taken = %s WHERE id = %s",
                (action, decision_id)
            )
            conn.commit()
            return self.get_ml_decision(decision_id)
        finally:
            cursor.close()
            conn.close()

    def create_pnl_event(self, event: PnLEvent) -> PnLEvent:
        """Record a P&L event."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = event.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            cursor.execute(
                f"INSERT INTO pnl_events ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            event.id = cursor.lastrowid
            conn.commit()
            return event
        finally:
            cursor.close()
            conn.close()

    def list_pnl_events(
        self,
        idea_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100
    ) -> List[PnLEvent]:
        """List P&L events with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM pnl_events WHERE 1=1"
            params = []

            if idea_id:
                query += " AND idea_id = %s"
                params.append(idea_id)
            if from_date:
                query += " AND DATE(event_time) >= %s"
                params.append(from_date)
            if to_date:
                query += " AND DATE(event_time) <= %s"
                params.append(to_date)

            query += " ORDER BY event_time DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [PnLEvent.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def compute_equity_curve(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[dict]:
        """Compute equity curve from P&L events."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            query = "SELECT event_time, pnl_delta FROM pnl_events WHERE 1=1"
            params = []

            if from_date:
                query += " AND DATE(event_time) >= %s"
                params.append(from_date)
            if to_date:
                query += " AND DATE(event_time) <= %s"
                params.append(to_date)

            query += " ORDER BY event_time ASC"

            cursor.execute(query, params)
            events = cursor.fetchall()

            curve = []
            cumulative_pnl = 0.0
            high_water = 0.0

            for e in events:
                cumulative_pnl += float(e['pnl_delta'])
                high_water = max(high_water, cumulative_pnl)
                drawdown = high_water - cumulative_pnl
                drawdown_pct = drawdown / high_water if high_water > 0 else 0

                curve.append({
                    'timestamp': e['event_time'].isoformat() if hasattr(e['event_time'], 'isoformat') else str(e['event_time']),
                    'cumulativePnl': cumulative_pnl,
                    'highWater': high_water,
                    'drawdown': drawdown,
                    'drawdownPct': drawdown_pct,
                })

            return curve
        finally:
            cursor.close()
            conn.close()

    def list_daily_performance(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 30
    ) -> List[DailyPerformance]:
        """List daily performance records."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM daily_performance WHERE 1=1"
            params = []

            if from_date:
                query += " AND date >= %s"
                params.append(from_date)
            if to_date:
                query += " AND date <= %s"
                params.append(to_date)

            query += " ORDER BY date DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [DailyPerformance.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def materialize_daily_performance(self, target_date: str) -> Optional[DailyPerformance]:
        """Materialize daily performance from P&L events."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            # Get daily metrics
            cursor.execute("""
                SELECT
                    SUM(pnl_delta) as net_pnl,
                    SUM(pnl_delta + fees + slippage) as gross_pnl,
                    SUM(fees) as total_fees,
                    COUNT(DISTINCT idea_id) as trade_count
                FROM pnl_events
                WHERE DATE(event_time) = %s
            """, (target_date,))
            daily = cursor.fetchone()

            if not daily or daily['net_pnl'] is None:
                return None

            # Get win/loss counts
            cursor.execute("""
                SELECT
                    COUNT(CASE WHEN total_pnl > 0 THEN 1 END) as win_count,
                    COUNT(CASE WHEN total_pnl <= 0 THEN 1 END) as loss_count
                FROM (
                    SELECT idea_id, SUM(pnl_delta) as total_pnl
                    FROM pnl_events
                    WHERE DATE(event_time) = %s
                    GROUP BY idea_id
                ) sub
            """, (target_date,))
            wl = cursor.fetchone()

            # Get high water and drawdown
            curve = self.compute_equity_curve(to_date=target_date)
            high_water = curve[-1]['highWater'] if curve else 0
            max_dd = max((c['drawdown'] for c in curve), default=0)
            max_dd_pct = max((c['drawdownPct'] for c in curve), default=0)

            # Get primary model used this day
            cursor.execute("""
                SELECT model_id, COUNT(*) as cnt
                FROM ml_decisions
                WHERE DATE(decision_time) = %s AND model_id IS NOT NULL
                GROUP BY model_id
                ORDER BY cnt DESC
                LIMIT 1
            """, (target_date,))
            model_row = cursor.fetchone()

            # Calculate ML contribution percentage
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN ml_score IS NOT NULL THEN 1 ELSE 0 END) as ml_count
                FROM ml_decisions
                WHERE DATE(decision_time) = %s
            """, (target_date,))
            ml_stats = cursor.fetchone()
            ml_contribution = (ml_stats['ml_count'] / ml_stats['total']) if ml_stats and ml_stats['total'] > 0 else 0

            # Upsert record
            cursor.execute("""
                INSERT INTO daily_performance
                    (date, net_pnl, gross_pnl, total_fees, high_water_pnl, max_drawdown, drawdown_pct,
                     trade_count, win_count, loss_count, primary_model_id, ml_contribution_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    net_pnl = VALUES(net_pnl),
                    gross_pnl = VALUES(gross_pnl),
                    total_fees = VALUES(total_fees),
                    high_water_pnl = VALUES(high_water_pnl),
                    max_drawdown = VALUES(max_drawdown),
                    drawdown_pct = VALUES(drawdown_pct),
                    trade_count = VALUES(trade_count),
                    win_count = VALUES(win_count),
                    loss_count = VALUES(loss_count),
                    primary_model_id = VALUES(primary_model_id),
                    ml_contribution_pct = VALUES(ml_contribution_pct)
            """, (
                target_date,
                daily['net_pnl'],
                daily['gross_pnl'],
                daily['total_fees'],
                high_water,
                max_dd,
                max_dd_pct,
                daily['trade_count'],
                wl['win_count'] if wl else 0,
                wl['loss_count'] if wl else 0,
                model_row['model_id'] if model_row else None,
                ml_contribution
            ))
            conn.commit()

            # Return the record
            cursor.execute("SELECT * FROM daily_performance WHERE date = %s", (target_date,))
            row = cursor.fetchone()
            return DailyPerformance.from_dict(row) if row else None
        finally:
            cursor.close()
            conn.close()

    def create_feature_snapshot(self, snapshot: MLFeatureSnapshot) -> MLFeatureSnapshot:
        """Create a feature snapshot."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = snapshot.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            cursor.execute(
                f"INSERT INTO ml_feature_snapshots ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            snapshot.id = cursor.lastrowid
            conn.commit()
            return snapshot
        finally:
            cursor.close()
            conn.close()

    def get_feature_snapshot(self, snapshot_id: int) -> Optional[MLFeatureSnapshot]:
        """Get a feature snapshot by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM ml_feature_snapshots WHERE id = %s", (snapshot_id,))
            row = cursor.fetchone()
            if row:
                return MLFeatureSnapshot.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def list_ml_models(self, status: Optional[str] = None, limit: int = 20) -> List[MLModel]:
        """List ML models."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM ml_models WHERE 1=1"
            params = []

            if status:
                query += " AND status = %s"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [MLModel.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def get_ml_model(self, model_id: int) -> Optional[MLModel]:
        """Get an ML model by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM ml_models WHERE id = %s", (model_id,))
            row = cursor.fetchone()
            if row:
                return MLModel.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_champion_model(self, regime: Optional[str] = None) -> Optional[MLModel]:
        """Get the current champion model, optionally for a specific regime."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM ml_models WHERE status = 'champion'"
            params = []

            if regime:
                query += " AND JSON_EXTRACT(hyperparameters, '$.regime') = %s"
                params.append(regime)
            else:
                query += " AND (JSON_EXTRACT(hyperparameters, '$.regime') IS NULL OR JSON_EXTRACT(hyperparameters, '$.regime') = 'all')"

            query += " ORDER BY deployed_at DESC LIMIT 1"

            cursor.execute(query, params)
            row = cursor.fetchone()
            if row:
                return MLModel.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def get_next_model_version(self, model_name: str) -> int:
        """Get the next version number for a model name."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COALESCE(MAX(model_version), 0) + 1 FROM ml_models WHERE model_name = %s",
                (model_name,)
            )
            return cursor.fetchone()[0]
        finally:
            cursor.close()
            conn.close()

    def create_ml_model(self, model: MLModel) -> MLModel:
        """Register a new ML model."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = model.to_dict()
            # Encode binary blob
            if isinstance(data.get('model_blob'), str):
                import base64
                data['model_blob'] = base64.b64decode(data['model_blob'])

            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            cursor.execute(
                f"INSERT INTO ml_models ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            model.id = cursor.lastrowid
            conn.commit()
            return model
        finally:
            cursor.close()
            conn.close()

    def deploy_ml_model(self, model_id: int) -> Optional[MLModel]:
        """Deploy a model as champion (retires current champion)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Retire current champion(s)
            cursor.execute(
                "UPDATE ml_models SET status = 'retired', retired_at = NOW() WHERE status = 'champion'"
            )

            # Promote new champion
            cursor.execute(
                "UPDATE ml_models SET status = 'champion', deployed_at = NOW() WHERE id = %s",
                (model_id,)
            )
            conn.commit()
            return self.get_ml_model(model_id)
        finally:
            cursor.close()
            conn.close()

    def retire_ml_model(self, model_id: int) -> Optional[MLModel]:
        """Retire a model."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE ml_models SET status = 'retired', retired_at = NOW() WHERE id = %s",
                (model_id,)
            )
            conn.commit()
            return self.get_ml_model(model_id)
        finally:
            cursor.close()
            conn.close()

    def list_experiments(self, status: Optional[str] = None, limit: int = 20) -> List[MLExperiment]:
        """List ML experiments."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM ml_experiments WHERE 1=1"
            params = []

            if status:
                query += " AND status = %s"
                params.append(status)

            query += " ORDER BY started_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            return [MLExperiment.from_dict(self._row_to_dict(cursor, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def get_experiment(self, experiment_id: int) -> Optional[MLExperiment]:
        """Get an ML experiment by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM ml_experiments WHERE id = %s", (experiment_id,))
            row = cursor.fetchone()
            if row:
                return MLExperiment.from_dict(self._row_to_dict(cursor, row))
            return None
        finally:
            cursor.close()
            conn.close()

    def create_experiment(self, experiment: MLExperiment) -> MLExperiment:
        """Create a new A/B experiment."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            data = experiment.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            cursor.execute(
                f"INSERT INTO ml_experiments ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            experiment.id = cursor.lastrowid
            conn.commit()
            return experiment
        finally:
            cursor.close()
            conn.close()

    def evaluate_experiment(self, experiment_id: int) -> Optional[dict]:
        """Evaluate experiment results."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            experiment = self.get_experiment(experiment_id)
            if not experiment:
                return None

            # Get outcomes by arm
            def get_outcomes(arm: str):
                cursor.execute("""
                    SELECT
                        d.idea_id,
                        d.original_score,
                        d.ml_score,
                        d.final_score,
                        t.settlement_pnl
                    FROM ml_decisions d
                    LEFT JOIN tracked_ideas t ON d.idea_id = t.id
                    WHERE d.experiment_id = %s
                      AND d.experiment_arm = %s
                      AND d.action_taken = 'traded'
                      AND t.settlement_status = 'settled'
                """, (experiment_id, arm))
                return cursor.fetchall()

            champion_outcomes = get_outcomes('champion')
            challenger_outcomes = get_outcomes('challenger')

            if not champion_outcomes or not challenger_outcomes:
                return {
                    'championMetrics': {'sampleCount': len(champion_outcomes)},
                    'challengerMetrics': {'sampleCount': len(challenger_outcomes)},
                    'pValue': 1.0,
                    'significant': False,
                    'winner': 'no_difference',
                }

            # Calculate metrics
            def calc_metrics(outcomes):
                wins = sum(1 for o in outcomes if (o.get('settlement_pnl') or 0) > 0)
                pnls = [float(o.get('settlement_pnl') or 0) for o in outcomes]
                return {
                    'winRate': wins / len(outcomes) if outcomes else 0,
                    'avgPnl': sum(pnls) / len(pnls) if pnls else 0,
                    'sampleCount': len(outcomes),
                }

            ch_metrics = calc_metrics(champion_outcomes)
            cl_metrics = calc_metrics(challenger_outcomes)

            # Simple p-value estimate (would use scipy in production)
            # For now, use a basic approximation
            p_value = 0.5  # Placeholder - real implementation would use statistical test

            return {
                'championMetrics': ch_metrics,
                'challengerMetrics': cl_metrics,
                'pValue': p_value,
                'significant': p_value < 0.05,
                'winner': 'challenger' if cl_metrics['avgPnl'] > ch_metrics['avgPnl'] and p_value < 0.05 else 'champion',
            }
        finally:
            cursor.close()
            conn.close()

    def conclude_experiment(
        self,
        experiment_id: int,
        winner: str,
        promote_challenger: bool = False
    ) -> Optional[MLExperiment]:
        """Conclude an experiment."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            experiment = self.get_experiment(experiment_id)
            if not experiment or experiment.status != 'running':
                return None

            cursor.execute(
                "UPDATE ml_experiments SET status = 'concluded', ended_at = NOW(), winner = %s WHERE id = %s",
                (winner, experiment_id)
            )

            if promote_challenger and winner == 'challenger':
                self.deploy_ml_model(experiment.challenger_model_id)

            conn.commit()
            return self.get_experiment(experiment_id)
        finally:
            cursor.close()
            conn.close()

    def abort_experiment(self, experiment_id: int, reason: Optional[str] = None) -> Optional[MLExperiment]:
        """Abort an experiment."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE ml_experiments SET status = 'aborted', ended_at = NOW() WHERE id = %s AND status = 'running'",
                (experiment_id,)
            )
            conn.commit()
            if cursor.rowcount > 0:
                return self.get_experiment(experiment_id)
            return None
        finally:
            cursor.close()
            conn.close()

    def get_circuit_breaker_status(self) -> dict:
        """Get circuit breaker status from settings/metrics."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            # Get daily P&L
            cursor.execute("""
                SELECT SUM(pnl_delta) as daily_pnl
                FROM pnl_events
                WHERE DATE(event_time) = CURDATE()
            """)
            daily = cursor.fetchone()

            # Get ML enabled setting
            ml_enabled = self.get_setting('ml_enabled')
            is_enabled = ml_enabled.value != 'false' if ml_enabled else True

            return {
                'dailyPnl': float(daily['daily_pnl'] or 0) if daily else 0,
                'mlEnabled': is_enabled,
                'breakers': {
                    'dailyLossLimit': {'triggered': False, 'threshold': 5000},
                    'maxDrawdown': {'triggered': False, 'threshold': 0.20},
                    'orderRate': {'triggered': False, 'threshold': 10},
                },
            }
        finally:
            cursor.close()
            conn.close()

    def check_circuit_breakers(self) -> dict:
        """Check all circuit breakers and return status."""
        status = self.get_circuit_breaker_status()

        triggered = []
        allow_trade = True
        action = 'allow'

        # Check daily loss limit
        if status['dailyPnl'] < -5000:
            triggered.append({'name': 'dailyLossLimit', 'severity': 'critical'})
            allow_trade = False
            action = 'block_all'

        # Check ML enabled
        if not status['mlEnabled']:
            triggered.append({'name': 'mlKillSwitch', 'severity': 'warning'})
            action = 'rules_only'

        return {
            'allowTrade': allow_trade,
            'triggeredBreakers': triggered,
            'action': action,
        }

    def set_ml_enabled(self, enabled: bool) -> None:
        """Set ML enabled/disabled setting."""
        setting = Setting(key='ml_enabled', value='true' if enabled else 'false')
        self.set_setting(setting)


class VersionConflictError(Exception):
    """Raised when a version conflict occurs during optimistic locking."""
    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__(f"Version conflict: current version is {current_version}")
