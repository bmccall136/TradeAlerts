import sqlite3

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [info[1] for info in cursor.fetchall()]

conn = sqlite3.connect("alerts_clean.db")
cursor = conn.cursor()

required_columns = {
    "time": "TEXT",
    "confidence": "INTEGER DEFAULT 100",
    "sparkline": "TEXT DEFAULT ''",
    "chart_url": "TEXT DEFAULT ''"
}

for column, col_type in required_columns.items():
    if not column_exists(cursor, "alerts", column):
        print(f"🔧 Adding missing column: {column}")
        cursor.execute(f"ALTER TABLE alerts ADD COLUMN {column} {col_type}")

conn.commit()
conn.close()

print("✅ Migration complete.")
