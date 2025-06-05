# File: init_alerts_db.py

import sqlite3
import shutil
import os

DB_FILE     = "alerts.db"
BACKUP_FILE = "alerts_backup.db"

def backup_db():
    if os.path.exists(DB_FILE):
        shutil.copy(DB_FILE, BACKUP_FILE)
        print(f"Backed up {DB_FILE} to {BACKUP_FILE}")

def nuke_and_rebuild():
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Drop alerts table if it exists
        c.execute("DROP TABLE IF EXISTS alerts;")
        # Drop indicator_settings table if it exists
        c.execute("DROP TABLE IF EXISTS indicator_settings;")

        # Recreate clean schema for alerts (now includes 'volume')
        c.execute("""
        CREATE TABLE alerts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT,
            timestamp TEXT,
            name      TEXT,
            price     REAL,
            triggers  TEXT,
            sparkline TEXT,
            vwap      REAL,
            vwap_diff REAL,
            volume    REAL,
            cleared   INTEGER DEFAULT 0
        );
        """)
        print("Recreated alerts table with volume column.")

        # Create the indicator_settings table (exactly one row with id=1).
        c.execute("""
        CREATE TABLE indicator_settings (
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
        print("Created indicator_settings table.")

        # Insert the single id=1 row (use INSERT OR IGNORE to avoid duplicates)
        c.execute("INSERT OR IGNORE INTO indicator_settings (id) VALUES (1);")
        print("Inserted id=1 into indicator_settings (defaults in place).")

        # Optionally: Insert a sample alert row (as before)
        c.execute("""
            INSERT INTO alerts 
              (symbol, timestamp, name, price, triggers, sparkline, vwap, vwap_diff, volume, cleared)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            'AAPL',
            '2025-05-29 16:00:00',
            'Apple Inc.',
            195.33,
            'MACD 🚀, VOL 🔊, BB 📈',
            '<svg width="60" height="16"><polyline points="1,15 10,10 20,12 30,7 40,9 50,4 59,8" style="fill:none;stroke:yellow;stroke-width:2"/></svg>',
            192.45,
            2.88,
            31200000  # sample volume
        ))
        print("Inserted sample alert row.")

        conn.commit()
        conn.close()

if __name__ == "__main__":
    backup_db()
    nuke_and_rebuild()
    print("Database schema reset complete!")
