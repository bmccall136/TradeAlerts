
import sqlite3

conn = sqlite3.connect("alerts_clean.db")
cursor = conn.cursor()

columns_to_add = [
    ("timestamp", "TEXT"),
    ("signal_type", "TEXT")
]

for column_name, column_type in columns_to_add:
    try:
        cursor.execute(f"ALTER TABLE alerts ADD COLUMN {column_name} {column_type};")
        print(f"✅ Added column: {column_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"⚠️ Column '{column_name}' already exists.")
        else:
            print(f"❌ Error adding column '{column_name}': {e}")

conn.commit()
conn.close()
