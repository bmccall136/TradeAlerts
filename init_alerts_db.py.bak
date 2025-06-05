import sqlite3
import shutil
import os

DB_FILE = "alerts.db"
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
        c.execute("DROP TABLE IF EXISTS alerts")
        # Recreate clean schema (now includes 'volume')
        c.execute("""
        CREATE TABLE alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp TEXT,
            name TEXT,
            price REAL,
            triggers TEXT,
            sparkline TEXT,
            vwap REAL,
            vwap_diff REAL,
            volume REAL,
            cleared INTEGER DEFAULT 0
        )
        """)
        conn.commit()
        print("Recreated alerts table with volume column.")

        # Insert a sample alert row
        c.execute("""
            INSERT INTO alerts (symbol, timestamp, name, price, triggers, sparkline, vwap, vwap_diff, volume, cleared)
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
        conn.commit()
        print("Inserted sample alert row.")
        conn.close()

if __name__ == "__main__":
    backup_db()
    nuke_and_rebuild()
    print("Database schema reset complete!")
