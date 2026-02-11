"""SQLite database schema and connection management."""

import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "db", "ascension_ads.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE(week_start)
);

CREATE TABLE IF NOT EXISTS campaign_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    campaign_name TEXT NOT NULL,
    impressions INTEGER,
    clicks INTEGER,
    spend REAL,
    sales REAL,
    orders INTEGER,
    ctr REAL,
    avg_cpc REAL,
    acos REAL,
    roas REAL,
    UNIQUE(snapshot_id, campaign_name)
);

CREATE TABLE IF NOT EXISTS target_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    campaign_name TEXT NOT NULL,
    targeting TEXT NOT NULL,
    target_type TEXT NOT NULL,
    match_type TEXT,
    bid REAL,
    impressions INTEGER,
    clicks INTEGER,
    spend REAL,
    sales REAL,
    orders INTEGER,
    ctr REAL,
    cpc REAL,
    conversion_rate REAL,
    UNIQUE(snapshot_id, campaign_name, targeting)
);

CREATE TABLE IF NOT EXISTS search_term_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    campaign_name TEXT NOT NULL,
    targeting TEXT NOT NULL,
    search_term TEXT NOT NULL,
    match_type TEXT,
    impressions INTEGER,
    clicks INTEGER,
    spend REAL,
    sales REAL,
    orders INTEGER,
    is_drift INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kdp_daily_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    format TEXT NOT NULL,
    units_sold INTEGER,
    net_units_sold INTEGER,
    royalty REAL,
    UNIQUE(snapshot_id, date, title, format)
);

CREATE TABLE IF NOT EXISTS bid_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES weekly_snapshots(id),
    targeting TEXT NOT NULL,
    current_bid REAL,
    recommended_max_bid REAL,
    conversion_rate REAL,
    flag TEXT
);
"""


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Get a SQLite connection, creating the database and schema if needed."""
    if db_path is None:
        db_path = os.path.normpath(DEFAULT_DB_PATH)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Create tables if they don't exist
    conn.executescript(SCHEMA)
    conn.commit()

    return conn
