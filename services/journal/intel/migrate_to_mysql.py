#!/usr/bin/env python3
# services/journal/intel/migrate_to_mysql.py
"""One-time migration script to transfer data from SQLite to MySQL."""

import sqlite3
import mysql.connector
from pathlib import Path
from typing import Dict, Any, List
import argparse
import sys


def get_sqlite_connection(db_path: str) -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_mysql_connection(config: Dict[str, Any]):
    """Get MySQL connection."""
    return mysql.connector.connect(
        host=config.get('host', 'localhost'),
        port=int(config.get('port', 3306)),
        user=config.get('user', 'journal'),
        password=config.get('password', ''),
        database=config.get('database', 'journal'),
        charset='utf8mb4'
    )


def table_has_data(mysql_conn, table_name: str) -> bool:
    """Check if MySQL table has any data."""
    cursor = mysql_conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0] > 0
    except mysql.connector.Error:
        return False
    finally:
        cursor.close()


def migrate_table(sqlite_conn: sqlite3.Connection, mysql_conn, table_name: str,
                  columns: List[str], skip_if_exists: bool = True):
    """Migrate a single table from SQLite to MySQL."""
    # Check if MySQL table already has data
    if skip_if_exists and table_has_data(mysql_conn, table_name):
        print(f"  Skipping {table_name} - already has data in MySQL")
        return 0

    # Read from SQLite
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()

    if not rows:
        print(f"  Skipping {table_name} - no data in SQLite")
        return 0

    # Insert into MySQL
    mysql_cursor = mysql_conn.cursor()
    placeholders = ', '.join(['%s'] * len(columns))
    column_names = ', '.join(f'`{c}`' if c == 'key' else c for c in columns)

    insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

    count = 0
    for row in rows:
        try:
            # Convert sqlite3.Row to list, handling None values
            values = [row[col] if col in row.keys() else None for col in columns]
            mysql_cursor.execute(insert_sql, values)
            count += 1
        except mysql.connector.IntegrityError as e:
            # Skip duplicates
            if 'Duplicate' in str(e):
                continue
            raise

    mysql_conn.commit()
    mysql_cursor.close()
    sqlite_cursor.close()

    print(f"  Migrated {count} rows to {table_name}")
    return count


def migrate(sqlite_path: str, mysql_config: Dict[str, Any], force: bool = False):
    """Migrate all data from SQLite to MySQL.

    Args:
        sqlite_path: Path to SQLite database file
        mysql_config: MySQL connection config (host, port, user, password, database)
        force: If True, migrate even if MySQL tables have data
    """
    print(f"SQLite source: {sqlite_path}")
    print(f"MySQL target: {mysql_config.get('user')}@{mysql_config.get('host')}:{mysql_config.get('port')}/{mysql_config.get('database')}")
    print()

    # Verify SQLite file exists
    if not Path(sqlite_path).exists():
        print(f"Error: SQLite database not found at {sqlite_path}")
        sys.exit(1)

    # Connect to both databases
    sqlite_conn = get_sqlite_connection(sqlite_path)
    mysql_conn = get_mysql_connection(mysql_config)

    try:
        print("Starting migration...")
        print()

        # Migration order matters due to foreign keys
        # 1. schema_version
        print("[1/6] schema_version")
        migrate_table(
            sqlite_conn, mysql_conn, 'schema_version',
            ['version'],
            skip_if_exists=not force
        )

        # 2. trade_logs (parent table)
        print("[2/6] trade_logs")
        migrate_table(
            sqlite_conn, mysql_conn, 'trade_logs',
            ['id', 'name', 'starting_capital', 'risk_per_trade', 'max_position_size',
             'intent', 'constraints', 'regime_assumptions', 'notes', 'is_active',
             'created_at', 'updated_at'],
            skip_if_exists=not force
        )

        # 3. trades (references trade_logs)
        print("[3/6] trades")
        migrate_table(
            sqlite_conn, mysql_conn, 'trades',
            ['id', 'log_id', 'symbol', 'underlying', 'strategy', 'side', 'strike',
             'width', 'dte', 'quantity', 'entry_time', 'entry_price', 'entry_spot',
             'entry_iv', 'exit_time', 'exit_price', 'exit_spot', 'planned_risk',
             'max_profit', 'max_loss', 'pnl', 'r_multiple', 'status', 'notes',
             'tags', 'source', 'playbook_id', 'created_at', 'updated_at'],
            skip_if_exists=not force
        )

        # 4. trade_events (references trades)
        print("[4/6] trade_events")
        migrate_table(
            sqlite_conn, mysql_conn, 'trade_events',
            ['id', 'trade_id', 'event_type', 'event_time', 'price', 'spot',
             'quantity_change', 'notes', 'created_at'],
            skip_if_exists=not force
        )

        # 5. symbols
        print("[5/6] symbols")
        migrate_table(
            sqlite_conn, mysql_conn, 'symbols',
            ['symbol', 'name', 'asset_type', 'multiplier', 'enabled', 'is_default',
             'created_at'],
            skip_if_exists=not force
        )

        # 6. settings
        print("[6/6] settings")
        migrate_table(
            sqlite_conn, mysql_conn, 'settings',
            ['key', 'value', 'category', 'scope', 'description', 'updated_at'],
            skip_if_exists=not force
        )

        print()
        print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        mysql_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        mysql_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Migrate journal data from SQLite to MySQL'
    )
    parser.add_argument(
        '--sqlite-path',
        default=str(Path(__file__).resolve().parents[1] / 'data' / 'journal.db'),
        help='Path to SQLite database (default: services/journal/data/journal.db)'
    )
    parser.add_argument(
        '--mysql-host',
        default='localhost',
        help='MySQL host (default: localhost)'
    )
    parser.add_argument(
        '--mysql-port',
        type=int,
        default=3306,
        help='MySQL port (default: 3306)'
    )
    parser.add_argument(
        '--mysql-user',
        default='journal',
        help='MySQL user (default: journal)'
    )
    parser.add_argument(
        '--mysql-password',
        default='',
        help='MySQL password (default: empty)'
    )
    parser.add_argument(
        '--mysql-database',
        default='journal',
        help='MySQL database (default: journal)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force migration even if MySQL tables have data'
    )

    args = parser.parse_args()

    mysql_config = {
        'host': args.mysql_host,
        'port': args.mysql_port,
        'user': args.mysql_user,
        'password': args.mysql_password,
        'database': args.mysql_database
    }

    migrate(args.sqlite_path, mysql_config, force=args.force)


if __name__ == '__main__':
    main()
