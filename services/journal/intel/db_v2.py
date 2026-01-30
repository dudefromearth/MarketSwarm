# services/journal/intel/db_v2.py
"""SQLite database operations for the FOTW Trade Log system (v2)."""

import sqlite3
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models_v2 import TradeLog, Trade, TradeEvent, EquityPoint, DrawdownPoint


class JournalDBv2:
    """SQLite database manager for FOTW trade logs."""

    SCHEMA_VERSION = 2

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = Path(__file__).resolve().parents[1]
            db_path = str(base / "data" / "journal.db")

        self.db_path = db_path
        self._ensure_dir()
        self._init_schema()

    def _ensure_dir(self):
        """Ensure the database directory exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _get_schema_version(self, conn: sqlite3.Connection) -> int:
        """Get current schema version from database."""
        try:
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0

    def _set_schema_version(self, conn: sqlite3.Connection, version: int):
        """Set schema version in database."""
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    def _init_schema(self):
        """Initialize or migrate the database schema."""
        conn = self._get_conn()
        try:
            current_version = self._get_schema_version(conn)

            if current_version < 2:
                self._migrate_to_v2(conn)

            conn.commit()
        finally:
            conn.close()

    def _migrate_to_v2(self, conn: sqlite3.Connection):
        """Migrate from v1 to v2 schema."""
        # Check if old trades table exists
        old_trades_exist = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trades'"
        ).fetchone() is not None

        # Check if we already have trade_logs (already migrated)
        logs_exist = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_logs'"
        ).fetchone() is not None

        if logs_exist:
            # Already migrated, just update version
            self._set_schema_version(conn, 2)
            return

        # Create new tables
        conn.executescript("""
            -- Trade Logs (containers with immutable params)
            CREATE TABLE IF NOT EXISTS trade_logs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,

                -- Immutable Starting Parameters
                starting_capital INTEGER NOT NULL,
                risk_per_trade INTEGER,
                max_position_size INTEGER,

                -- Metadata
                intent TEXT,
                constraints TEXT,
                regime_assumptions TEXT,
                notes TEXT,

                -- Status
                is_active INTEGER DEFAULT 1,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Trade Events (lifecycle audit trail)
            CREATE TABLE IF NOT EXISTS trade_events (
                id TEXT PRIMARY KEY,
                trade_id TEXT NOT NULL,

                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,

                price INTEGER,
                spot REAL,
                quantity_change INTEGER,
                notes TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_events_trade ON trade_events(trade_id);
        """)

        if old_trades_exist:
            # Migrate existing trades
            self._migrate_trades_v1_to_v2(conn)
        else:
            # Create fresh trades table
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    log_id TEXT NOT NULL,

                    symbol TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    strike REAL NOT NULL,
                    width INTEGER,
                    dte INTEGER,
                    quantity INTEGER NOT NULL DEFAULT 1,

                    entry_time TEXT NOT NULL,
                    entry_price INTEGER NOT NULL,
                    entry_spot REAL,
                    entry_iv REAL,

                    exit_time TEXT,
                    exit_price INTEGER,
                    exit_spot REAL,

                    planned_risk INTEGER,
                    max_profit INTEGER,
                    max_loss INTEGER,

                    pnl INTEGER,
                    r_multiple REAL,

                    status TEXT DEFAULT 'open',

                    notes TEXT,
                    tags TEXT,
                    source TEXT DEFAULT 'manual',
                    playbook_id TEXT,

                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (log_id) REFERENCES trade_logs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_log_status ON trades(log_id, status);
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
            """)

        self._set_schema_version(conn, 2)

    def _migrate_trades_v1_to_v2(self, conn: sqlite3.Connection):
        """Migrate existing v1 trades to v2 schema."""
        # Check if old trades have user_id column (v1 schema)
        cursor = conn.execute("PRAGMA table_info(trades)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'log_id' in columns:
            # Already migrated
            return

        # Create a default trade log for existing trades
        default_log_id = TradeLog.new_id()
        now = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT INTO trade_logs (id, name, starting_capital, intent, created_at, updated_at)
            VALUES (?, 'Default Log', 2500000, 'Migrated from v1', ?, ?)
        """, (default_log_id, now, now))

        # Rename old trades table
        conn.execute("ALTER TABLE trades RENAME TO trades_v1")

        # Create new trades table
        conn.executescript("""
            CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                log_id TEXT NOT NULL,

                symbol TEXT NOT NULL,
                underlying TEXT NOT NULL,
                strategy TEXT NOT NULL,
                side TEXT NOT NULL,
                strike REAL NOT NULL,
                width INTEGER,
                dte INTEGER,
                quantity INTEGER NOT NULL DEFAULT 1,

                entry_time TEXT NOT NULL,
                entry_price INTEGER NOT NULL,
                entry_spot REAL,
                entry_iv REAL,

                exit_time TEXT,
                exit_price INTEGER,
                exit_spot REAL,

                planned_risk INTEGER,
                max_profit INTEGER,
                max_loss INTEGER,

                pnl INTEGER,
                r_multiple REAL,

                status TEXT DEFAULT 'open',

                notes TEXT,
                tags TEXT,
                source TEXT DEFAULT 'manual',
                playbook_id TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (log_id) REFERENCES trade_logs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_trades_log_status ON trades(log_id, status);
            CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
        """)

        # Migrate data from v1 to v2
        # Convert prices from dollars to cents
        conn.execute(f"""
            INSERT INTO trades (
                id, log_id, symbol, underlying, strategy, side, strike, width, dte, quantity,
                entry_time, entry_price, entry_spot, exit_time, exit_price, exit_spot,
                max_profit, max_loss, pnl, status, notes, tags, source, playbook_id,
                created_at, updated_at
            )
            SELECT
                id, ?, symbol, underlying, strategy, side, strike, width, dte, quantity,
                entry_time,
                CAST(entry_price * 100 AS INTEGER),
                entry_spot,
                exit_time,
                CASE WHEN exit_price IS NOT NULL THEN CAST(exit_price * 100 AS INTEGER) END,
                exit_spot,
                CASE WHEN max_profit IS NOT NULL THEN CAST(max_profit * 100 AS INTEGER) END,
                CASE WHEN max_loss IS NOT NULL THEN CAST(max_loss * 100 AS INTEGER) END,
                CASE WHEN pnl IS NOT NULL THEN CAST(pnl AS INTEGER) END,
                status, notes, tags, source, playbook_id,
                created_at, updated_at
            FROM trades_v1
        """, (default_log_id,))

        # Create OPEN events for all trades
        trades = conn.execute("SELECT id, entry_time, entry_price, entry_spot FROM trades").fetchall()
        for trade in trades:
            event_id = TradeEvent.new_id()
            conn.execute("""
                INSERT INTO trade_events (id, trade_id, event_type, event_time, price, spot, created_at)
                VALUES (?, ?, 'open', ?, ?, ?, ?)
            """, (event_id, trade[0], trade[1], trade[2], trade[3], now))

        # Create CLOSE events for closed trades
        closed_trades = conn.execute(
            "SELECT id, exit_time, exit_price, exit_spot FROM trades WHERE status = 'closed'"
        ).fetchall()
        for trade in closed_trades:
            event_id = TradeEvent.new_id()
            conn.execute("""
                INSERT INTO trade_events (id, trade_id, event_type, event_time, price, spot, created_at)
                VALUES (?, ?, 'close', ?, ?, ?, ?)
            """, (event_id, trade[0], trade[1], trade[2], trade[3], now))

        # Drop old table
        conn.execute("DROP TABLE trades_v1")

    # ==================== Trade Log CRUD ====================

    def create_log(self, log: TradeLog) -> TradeLog:
        """Create a new trade log."""
        conn = self._get_conn()
        try:
            data = log.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join('?' * len(data))

            conn.execute(
                f"INSERT INTO trade_logs ({columns}) VALUES ({placeholders})",
                list(data.values())
            )
            conn.commit()
            return log
        finally:
            conn.close()

    def get_log(self, log_id: str) -> Optional[TradeLog]:
        """Get a single trade log by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM trade_logs WHERE id = ? AND is_active = 1",
                (log_id,)
            ).fetchone()

            if row:
                return TradeLog.from_dict(dict(row))
            return None
        finally:
            conn.close()

    def list_logs(self, include_inactive: bool = False) -> List[TradeLog]:
        """List all trade logs."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM trade_logs"
            if not include_inactive:
                query += " WHERE is_active = 1"
            query += " ORDER BY created_at DESC"

            rows = conn.execute(query).fetchall()
            return [TradeLog.from_dict(dict(row)) for row in rows]
        finally:
            conn.close()

    def update_log(self, log_id: str, updates: Dict[str, Any]) -> Optional[TradeLog]:
        """Update a trade log (metadata only, not starting params)."""
        conn = self._get_conn()
        try:
            # Prevent updating immutable fields
            immutable = {'starting_capital', 'risk_per_trade', 'max_position_size', 'id', 'created_at'}
            updates = {k: v for k, v in updates.items() if k not in immutable}

            if not updates:
                return self.get_log(log_id)

            updates['updated_at'] = datetime.utcnow().isoformat()

            set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
            params = list(updates.values()) + [log_id]

            conn.execute(
                f"UPDATE trade_logs SET {set_clause} WHERE id = ?",
                params
            )
            conn.commit()

            return self.get_log(log_id)
        finally:
            conn.close()

    def delete_log(self, log_id: str) -> bool:
        """Soft delete a trade log."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE trade_logs SET is_active = 0, updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), log_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_log_summary(self, log_id: str) -> Dict[str, Any]:
        """Get a log with trade counts."""
        conn = self._get_conn()
        try:
            log = self.get_log(log_id)
            if not log:
                return {}

            counts = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status = 'closed' THEN pnl ELSE 0 END) as total_pnl
                FROM trades WHERE log_id = ?
            """, (log_id,)).fetchone()

            return {
                **log.to_api_dict(),
                'total_trades': counts[0] or 0,
                'open_trades': counts[1] or 0,
                'closed_trades': counts[2] or 0,
                'total_pnl': counts[3] or 0,
                'total_pnl_dollars': (counts[3] or 0) / 100
            }
        finally:
            conn.close()

    # ==================== Trade CRUD ====================

    def create_trade(self, trade: Trade) -> Trade:
        """Create a new trade and auto-create OPEN event."""
        conn = self._get_conn()
        try:
            # Insert trade
            data = trade.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join('?' * len(data))

            conn.execute(
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
            event_placeholders = ', '.join('?' * len(event_data))

            conn.execute(
                f"INSERT INTO trade_events ({event_columns}) VALUES ({event_placeholders})",
                list(event_data.values())
            )

            conn.commit()
            return trade
        finally:
            conn.close()

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get a single trade by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM trades WHERE id = ?",
                (trade_id,)
            ).fetchone()

            if row:
                return Trade.from_dict(dict(row))
            return None
        finally:
            conn.close()

    def get_trade_with_events(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get a trade with all its events."""
        conn = self._get_conn()
        try:
            trade = self.get_trade(trade_id)
            if not trade:
                return None

            events = conn.execute(
                "SELECT * FROM trade_events WHERE trade_id = ? ORDER BY event_time ASC",
                (trade_id,)
            ).fetchall()

            return {
                **trade.to_api_dict(),
                'events': [TradeEvent.from_dict(dict(e)).to_api_dict() for e in events]
            }
        finally:
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
        try:
            query = "SELECT * FROM trades WHERE log_id = ?"
            params: List[Any] = [log_id]

            if status and status != "all":
                query += " AND status = ?"
                params.append(status)

            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)

            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)

            if from_date:
                query += " AND entry_time >= ?"
                params.append(from_date)

            if to_date:
                query += " AND entry_time <= ?"
                params.append(to_date)

            query += " ORDER BY entry_time DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [Trade.from_dict(dict(row)) for row in rows]
        finally:
            conn.close()

    def update_trade(self, trade_id: str, updates: Dict[str, Any]) -> Optional[Trade]:
        """Update a trade with the given fields."""
        conn = self._get_conn()
        try:
            updates['updated_at'] = datetime.utcnow().isoformat()

            set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
            params = list(updates.values()) + [trade_id]

            conn.execute(
                f"UPDATE trades SET {set_clause} WHERE id = ?",
                params
            )
            conn.commit()

            return self.get_trade(trade_id)
        finally:
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
            placeholders = ', '.join('?' * len(data))

            conn.execute(
                f"INSERT INTO trade_events ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            # Update trade quantity
            new_quantity = trade.quantity + quantity_change
            conn.execute(
                "UPDATE trades SET quantity = ?, updated_at = ? WHERE id = ?",
                (new_quantity, datetime.utcnow().isoformat(), trade_id)
            )

            conn.commit()
            return event
        finally:
            conn.close()

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

        # Calculate P&L
        pnl = (exit_price - trade.entry_price) * trade.quantity
        r_multiple = None
        if trade.planned_risk and trade.planned_risk > 0:
            r_multiple = pnl / trade.planned_risk

        conn = self._get_conn()
        try:
            # Update trade
            conn.execute("""
                UPDATE trades SET
                    exit_time = ?, exit_price = ?, exit_spot = ?,
                    pnl = ?, r_multiple = ?, status = 'closed', updated_at = ?
                WHERE id = ?
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
            placeholders = ', '.join('?' * len(data))

            conn.execute(
                f"INSERT INTO trade_events ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            conn.commit()
            return self.get_trade(trade_id)
        finally:
            conn.close()

    def delete_trade(self, trade_id: str) -> bool:
        """Delete a trade and its events."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM trade_events WHERE trade_id = ?", (trade_id,))
            cursor = conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ==================== Events ====================

    def get_trade_events(self, trade_id: str) -> List[TradeEvent]:
        """Get all events for a trade."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM trade_events WHERE trade_id = ? ORDER BY event_time ASC",
                (trade_id,)
            ).fetchall()
            return [TradeEvent.from_dict(dict(row)) for row in rows]
        finally:
            conn.close()

    # ==================== Analytics Helpers ====================

    def get_closed_trades_for_equity(
        self,
        log_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Trade]:
        """Get closed trades ordered by exit time for equity curve."""
        conn = self._get_conn()
        try:
            query = """
                SELECT * FROM trades
                WHERE log_id = ? AND status = 'closed' AND exit_time IS NOT NULL
            """
            params: List[Any] = [log_id]

            if from_date:
                query += " AND exit_time >= ?"
                params.append(from_date)

            if to_date:
                query += " AND exit_time <= ?"
                params.append(to_date)

            query += " ORDER BY exit_time ASC"

            rows = conn.execute(query, params).fetchall()
            return [Trade.from_dict(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_log_stats(self, log_id: str) -> Dict[str, Any]:
        """Get basic statistics for a log."""
        conn = self._get_conn()
        try:
            log = self.get_log(log_id)
            if not log:
                return {}

            # Total counts
            counts = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count
                FROM trades WHERE log_id = ?
            """, (log_id,)).fetchone()

            # P&L stats
            pnl_stats = conn.execute("""
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
                WHERE log_id = ? AND status = 'closed'
            """, (log_id,)).fetchone()

            # Date range
            dates = conn.execute("""
                SELECT MIN(entry_time), MAX(COALESCE(exit_time, entry_time))
                FROM trades WHERE log_id = ?
            """, (log_id,)).fetchone()

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
            conn.close()
