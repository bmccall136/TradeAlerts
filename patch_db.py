import sqlite3

conn = sqlite3.connect("alerts.db")
cursor = conn.cursor()

# Add all expected columns if they aren't already in the table
columns = [
    ("alert_type", "TEXT"),
    ("confidence", "REAL"),
    ("cleared", "INTEGER"),
    ("name", "TEXT"),
    ("qty", "INTEGER")
]

for column, col_type in columns:
    try:
        cursor.execute(f"ALTER TABLE alerts ADD COLUMN {column} {col_type}")
        print(f"✅ '{column}' column added.")
    except sqlite3.OperationalError as e:
        print(f"⚠️ '{column}' may already exist or another error occurred: {e}")

conn.commit()
conn.close()
