import os
import sqlite3

DB_PATH = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

def main() -> None:
    print(f"Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # List tables
    print("\nTables:")
    for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        print(" -", name)

    # Basic stats for realized_trades
    try:
        cur.execute("SELECT COUNT(*), COALESCE(SUM(gain), 0) FROM realized_trades")
        count, total_gain = cur.fetchone()
        print(f"\nrealized_trades rows: {count}, total gain: {total_gain}")
    except sqlite3.OperationalError as e:
        print("\n[!] realized_trades table missing or mis-named:", e)
        conn.close()
        return

    print("\nColumns in realized_trades:")
    cur.execute("PRAGMA table_info(realized_trades)")
    for cid, name, ctype, notnull, dflt, pk in cur.fetchall():
        print(f" - {name} ({ctype})")

    print("\nMost recent 10 realized trades:")
    try:
        cur.execute(
            "SELECT * FROM realized_trades ORDER BY close_date DESC LIMIT 10"
        )
    except sqlite3.OperationalError:
        # If close_date isn't a column, just dump unsorted
        cur.execute("SELECT * FROM realized_trades LIMIT 10")

    rows = cur.fetchall()
    for r in rows:
        print(r)

    conn.close()

if __name__ == "__main__":
    main()
