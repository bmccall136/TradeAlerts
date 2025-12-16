import sqlite3

DB = r"C:\TradeAlerts\live.db"

# E*TRADE Gains & Losses for 2025-11-26 (from your Gains & Losses export)
# symbol, qty, open_date, close_date, cost_share, price_share, gain, term
TRADES = [
    ("STZ",  1.0, "2025-11-25", "2025-11-26 11:46:45", 132.15, 135.80,  3.65, "Short"),
    ("ANET", 1.0, "2025-11-15", "2025-11-26 11:46:47", 134.89, 127.62, -7.27, "Short"),
    ("BBY",  1.0, "2025-11-24", "2025-11-26 13:13:25",  81.13,  81.33,  0.20, "Short"),
    ("KMB",  1.0, "2025-11-25", "2025-11-26 11:47:49", 106.00, 108.93,  2.93, "Short"),
    ("LYV",  1.0, "2025-11-25", "2025-11-26 13:13:57", 128.63, 131.42,  2.79, "Short"),
    ("STT",  1.0, "2025-11-24", "2025-11-26 11:46:49", 115.33, 117.91,  2.58, "Short"),
    ("ALB",  1.0, "2025-11-18", "2025-11-26 11:46:48", 128.13, 126.60, -1.53, "Short"),
]


def main() -> None:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # 1) Clean out any existing rows for these exact sells
    #    (prevents duplicate P&L if you re-run the script)
    # ------------------------------------------------------------------
    print("Cleaning existing realized_trades rows for 2025-11-26 backfill…")
    for sym, qty, open_date, close_date, cost_share, price_share, gain, term in TRADES:
        cur.execute(
            """
            DELETE FROM realized_trades
            WHERE symbol = ?
              AND close_date = ?
              AND action = 'SELL'
            """,
            (sym, close_date),
        )
        deleted = cur.rowcount
        if deleted:
            print(f"  - Deleted {deleted} old row(s) for {sym} @ {close_date}")

    # ------------------------------------------------------------------
    # 2) Insert corrected FIFO / E*TRADE-aligned rows
    # ------------------------------------------------------------------
    print("Inserting corrected realized trades for 2025-11-26…")
    for sym, qty, open_date, close_date, cost_share, price_share, gain, term in TRADES:
        total_cost = round(cost_share * qty, 2)
        proceeds = round(price_share * qty, 2)

        print(
            f"  -> {sym}: qty={qty}, cost_share={cost_share}, "
            f"price_share={price_share}, gain={gain}"
        )

        cur.execute(
            """
            INSERT INTO realized_trades
            (symbol, action, qty, open_date, close_date,
             price_share, proceeds, cost_share, total_cost, gain, term)
            VALUES (?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sym,
                qty,
                open_date,
                close_date,
                price_share,
                proceeds,
                cost_share,
                total_cost,
                gain,
                term,
            ),
        )

    conn.commit()
    conn.close()
    print("Done. Refresh your dashboard Day/Week/Month tiles to verify.")


if __name__ == "__main__":
    main()
