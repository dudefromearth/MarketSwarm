# services/journal/intel/db_v2.py
"""MySQL database operations for the FOTW Trade Log system (v2)."""

import mysql.connector
from mysql.connector import pooling
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models_v2 import TradeLog, Trade, TradeEvent, EquityPoint, DrawdownPoint, Symbol, Setting


class JournalDBv2:
    """MySQL database manager for FOTW trade logs."""

    SCHEMA_VERSION = 3

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

    def get_log(self, log_id: str) -> Optional[TradeLog]:
        """Get a single trade log by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
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

    def list_logs(self, include_inactive: bool = False) -> List[TradeLog]:
        """List all trade logs."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = "SELECT * FROM trade_logs"
            if not include_inactive:
                query += " WHERE is_active = 1"
            query += " ORDER BY created_at DESC"

            cursor.execute(query)
            rows = cursor.fetchall()
            return [TradeLog.from_dict(self._row_to_dict(cursor, row)) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def update_log(self, log_id: str, updates: Dict[str, Any]) -> Optional[TradeLog]:
        """Update a trade log (metadata only, not starting params)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Prevent updating immutable fields
            immutable = {'starting_capital', 'risk_per_trade', 'max_position_size', 'id', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_log(log_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
            params = list(updates.values()) + [log_id]

            cursor.execute(
                f"UPDATE trade_logs SET {set_clause} WHERE id = %s",
                params
            )
            conn.commit()

            return self.get_log(log_id)
        finally:
            cursor.close()
            conn.close()

    def delete_log(self, log_id: str) -> bool:
        """Soft delete a trade log."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE trade_logs SET is_active = 0, updated_at = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), log_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def get_log_summary(self, log_id: str) -> Dict[str, Any]:
        """Get a log with trade counts."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            log = self.get_log(log_id)
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

    def get_log_stats(self, log_id: str) -> Dict[str, Any]:
        """Get basic statistics for a log."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            log = self.get_log(log_id)
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
