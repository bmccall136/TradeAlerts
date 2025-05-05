import sqlite3

conn = sqlite3.connect("alerts_clean.db")
c = conn.cursor()

c.execute("""
  DELETE FROM alerts
   WHERE symbol   IS NULL
      OR name     IS NULL
      OR signal   IS NULL
      OR timestamp IS NULL
      OR confidence IS NULL
      OR price    IS NULL
      OR sparkline IS NULL
""")

conn.commit()
conn.close()
print("✅ Removed malformed rows.")
