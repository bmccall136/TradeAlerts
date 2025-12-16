import sqlite3
import os

DB_PATH = r"C:\TradeAlerts\live.db"

# (symbol, close_date, qty, price_share, cost_share, gain)
TRADES = [
    ("DVA",  "2025-11-24 15:09:14", 1.0, 120.28, 121.47, -1.19),
    ("MRNA", "2025-11-24 14:48:51", 6.0,  24.01,  24.26, -1.50),
    ("EXC",  "2025-11-24 11:29:53", 1.0,  45.76,  46.74, -0.98),
    ("BBY",  "2025-11-24 11:29:52", 1.0,  76.60,  76.48,  0.12),
    ("CVS",  "2025-11-24 11:29:50", 1.0,  78.28,   0.00, 78.28),
    ("AES",  "2025-11-24 11:29:49",11.0,  13.83,  14.09, -2.91),
    ("ANET", "2025-11-24 11:29:47", 2.0, 121.23, 131.28, -20.11),
    ("INTC", "2025-11-24 11:29:46", 8.0,  35.95,  35.60,  2.76),
    ("ALB",  "2025-11-24 11:29:45", 5.0, 115.72, 124.18, -42.30),
]

def main():
    print(f"Using DB: {os.path.abspath(DB_PATH)}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Quick sanity check
    cur.execute("PRAGMA table_info(realized_trades)")
    cols = [c[1] for c in cur.fetchall()]
    print("realized_trades columns:", cols)

    for sym, close_dt, qty, price_share, cost_share, gain in TRADES:
        # Avoid double-insert: check for existing row with same symbol/close_date/gain
        cur.execute(
            """
            SELECT id FROM realized_trades
            WHERE symbol = ? AND action = 'SELL'
              AND close_date = ? AND ABS(gain - ?) < 0.01
            """,
            (sym, close_dt, gain),
        )
        existing = cur.fetchone()
        if existing:
            print(f"Skipping {sym} @ {close_dt} (already id={existing[0]})")
            continue

        proceeds   = price_share * qty
        total_cost = cost_share * qty
        open_dt    = close_dt  # we don't know the true open date; this keeps it non-null

        cur.execute(
            """
            INSERT INTO realized_trades
                (symbol, action, qty,
                 open_date, close_date,
                 price_share, proceeds,
                 cost_share, total_cost,
                 gain, term)
            VALUES (?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sym, qty,
                open_dt, close_dt,
                price_share, proceeds,
                cost_share, total_cost,
                gain, "DAY",
            ),
        )
        print(f"Inserted realized SELL for {sym} ({qty} shares) at {close_dt}, gain={gain}")

    conn.commit()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
