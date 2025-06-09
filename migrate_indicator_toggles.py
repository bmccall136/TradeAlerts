#!/usr/bin/env python3
"""
migrate_indicator_toggles.py

Connects to alerts.db, enables WAL journaling, and adds the
sma_on, rsi_on, macd_on, bb_on, vol_on, vwap_on columns
if they don’t already exist (with the defaults you want).
"""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "alerts.db"

def main():
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    cur = conn.cursor()

    # Ensure the settings table exists (if you haven't already run init_alerts_db.py)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS indicator_settings (
      id                INTEGER PRIMARY KEY CHECK(id = 1),
      match_count       INTEGER NOT NULL DEFAULT 1,
      sma_length        INTEGER NOT NULL DEFAULT 20,
      rsi_len           INTEGER NOT NULL DEFAULT 14,
      rsi_overbought    INTEGER NOT NULL DEFAULT 70,
      rsi_oversold      INTEGER NOT NULL DEFAULT 30,
      macd_fast         INTEGER NOT NULL DEFAULT 12,
      macd_slow         INTEGER NOT NULL DEFAULT 26,
      macd_signal       INTEGER NOT NULL DEFAULT 9,
      bb_length         INTEGER NOT NULL DEFAULT 20,
      bb_std            REAL    NOT NULL DEFAULT 2.0,
      vol_multiplier    REAL    NOT NULL DEFAULT 1.0,
      vwap_threshold    REAL    NOT NULL DEFAULT 0.0,
      news_on           INTEGER NOT NULL DEFAULT 0
    );
    """)
    # Make sure there's at least one row to ALTER
    cur.execute("INSERT OR IGNORE INTO indicator_settings (id) VALUES (1);")

    # Fetch existing columns
    cur.execute("PRAGMA table_info(indicator_settings);")
    existing = {row[1] for row in cur.fetchall()}

    # Toggles to add: default SMA & VWAP on, everything else off
    toggles = {
        "sma_on":  "INTEGER NOT NULL DEFAULT 1",
        "rsi_on":  "INTEGER NOT NULL DEFAULT 0",
        "macd_on": "INTEGER NOT NULL DEFAULT 0",
        "bb_on":   "INTEGER NOT NULL DEFAULT 0",
        "vol_on":  "INTEGER NOT NULL DEFAULT 0",
        "vwap_on": "INTEGER NOT NULL DEFAULT 1",
    }

    for col, definition in toggles.items():
        if col not in existing:
            print(f"Adding column {col}...")
            cur.execute(f"ALTER TABLE indicator_settings ADD COLUMN {col} {definition};")
        else:
            print(f"Column {col} already exists, skipping.")

    conn.commit()
    conn.close()
    print("✅ Migration complete.")

if __name__ == "__main__":
    main()
