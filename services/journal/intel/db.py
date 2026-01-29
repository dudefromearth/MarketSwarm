# services/journal/intel/db.py
"""SQLite database operations for the journal service."""

import sqlite3
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models import Trade


class JournalDB:
    """SQLite database manager for trades."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to services/journal/data/journal.db
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
        return conn

    def _init_schema(self):
        """Initialize the database schema."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',

                    -- Position details
                    symbol TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    dte INTEGER,
                    strike REAL NOT NULL,
                    width INTEGER,
                    quantity INTEGER NOT NULL DEFAULT 1,

                    -- Entry
                    entry_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_spot REAL,

                    -- Exit (nullable until closed)
                    exit_time TEXT,
                    exit_price REAL,
                    exit_spot REAL,

                    -- Calculated
                    pnl REAL,
                    pnl_percent REAL,
                    max_profit REAL,
                    max_loss REAL,

                    -- Status
                    status TEXT DEFAULT 'open',

                    -- Metadata
                    notes TEXT,
                    tags TEXT,
                    playbook_id TEXT,
                    source TEXT DEFAULT 'manual',

                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_trades_user_status ON trades(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            """)
            conn.commit()
        finally:
            conn.close()

    def create_trade(self, trade: Trade) -> Trade:
        """Insert a new trade."""
        conn = self._get_conn()
        try:
            data = trade.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join('?' * len(data))

            conn.execute(
                f"INSERT INTO trades ({columns}) VALUES ({placeholders})",
                list(data.values())
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

    def list_trades(
        self,
        user_id: str = "default",
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Trade]:
        """List trades with optional filters."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM trades WHERE user_id = ?"
            params: List[Any] = [user_id]

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
            # Add updated_at timestamp
            updates['updated_at'] = datetime.utcnow().isoformat()

            # Build SET clause
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

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_spot: Optional[float] = None,
        exit_time: Optional[str] = None
    ) -> Optional[Trade]:
        """Close a trade and calculate P&L."""
        trade = self.get_trade(trade_id)
        if not trade:
            return None

        if exit_time is None:
            exit_time = datetime.utcnow().isoformat()

        # Calculate P&L
        pnl = (exit_price - trade.entry_price) * 100 * trade.quantity
        pnl_percent = None
        if trade.entry_price > 0:
            pnl_percent = ((exit_price - trade.entry_price) / trade.entry_price) * 100

        updates = {
            'exit_time': exit_time,
            'exit_price': exit_price,
            'exit_spot': exit_spot,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'status': 'closed'
        }

        return self.update_trade(trade_id, updates)

    def delete_trade(self, trade_id: str) -> bool:
        """Delete a trade."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM trades WHERE id = ?",
                (trade_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_closed_trades_for_equity(
        self,
        user_id: str = "default",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Trade]:
        """Get closed trades ordered by exit time for equity curve."""
        conn = self._get_conn()
        try:
            query = """
                SELECT * FROM trades
                WHERE user_id = ? AND status = 'closed' AND exit_time IS NOT NULL
            """
            params: List[Any] = [user_id]

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

    def get_stats(self, user_id: str = "default") -> Dict[str, Any]:
        """Get basic statistics for a user."""
        conn = self._get_conn()
        try:
            # Total counts
            total = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE user_id = ?",
                (user_id,)
            ).fetchone()[0]

            open_count = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status = 'open'",
                (user_id,)
            ).fetchone()[0]

            closed_count = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status = 'closed'",
                (user_id,)
            ).fetchone()[0]

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
                    AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss
                FROM trades
                WHERE user_id = ? AND status = 'closed'
            """, (user_id,)).fetchone()

            return {
                'total_trades': total,
                'open_trades': open_count,
                'closed_trades': closed_count,
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
            }
        finally:
            conn.close()
