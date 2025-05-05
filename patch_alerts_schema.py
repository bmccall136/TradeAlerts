import sqlite3

conn = sqlite3.connect("alerts_clean.db")
cursor = conn.cursor()

# Rename 'time' column to 'timestamp'
try:
    cursor.execute("ALTER TABLE alerts RENAME TO alerts_old;")
    cursor.execute("""
        CREATE TABLE alerts (
            symbol TEXT,
            name TEXT,
            signal TEXT,
            timestamp TEXT,
            confidence INTEGER,
            price REAL,
            sparkline TEXT,
            chart_url TEXT,
            signal_type TEXT
        );
    """)
    cursor.execute("""
        INSERT INTO alerts (symbol, name, signal, timestamp, confidence)
        SELECT symbol, name, signal, time, confidence FROM alerts_old;
    """)
    cursor.execute("DROP TABLE alerts_old;")
    print("✅ Schema fixed and 'timestamp' added.")
except Exception as e:
    print(f"❌ Failed to patch schema: {e}")

conn.commit()
conn.close()