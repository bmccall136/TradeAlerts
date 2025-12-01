import sqlite3

DB = r"C:\TradeAlerts\live.db"

# E*TRADE Gains & Losses for 2025-11-25 sells (from your CSV)
# symbol, qty, open_date, close_date, cost_share, price_share, gain, term
TRADES = [
    # HOOD: 2 shares total; total cost 226.56; proceeds 231.15; gain 4.59
    # We'll use averaged per-share values; UI will show rounded numbers.
    ("HOOD", 2.0, "2025-11-25", "2025-11-25 14:51:24",
     226.56 / 2.0, 231.15 / 2.0, 4.59, "Short"),

    # PNR: 1 share; total cost 106.79; proceeds 105.69; gain -1.10
    ("PNR", 1.0, "2025-11-25", "2025-11-25 14:41:41",
     106.79, 105.69, -1.10, "Short"),

    # MCHP: 2 shares; total cost 104.93; proceeds 103.09; gain -1.84
    ("MCHP", 2.0, "2025-11-25", "2025-11-25 13:11:14",
     104.93 / 2.0, 103.09 / 2.0, -1.84, "Short"),

    # IPG: 5 shares; total cost 129.43; proceeds 125.58; gain -3.85
    ("IPG", 5.0, "2025-11-25", "2025-11-25 12:28:18",
     129.43 / 5.0, 125.58 / 5.0, -3.85, "Short"),
]


def main() -> None:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    print("Cleaning existing realized_trades rows for 2025-11-25 backfill…")
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

    print("Inserting corrected realized trades for 2025-11-25…")
    for sym, qty, open_date, close_date, cost_share, price_share, gain, term in TRADES:
        total_cost = round(cost_share * qty, 2)
        proceeds = round(price_share * qty, 2)

        print(
            f"  -> {sym}: qty={qty}, cost_share={cost_share:.4f}, "
            f"price_share={price_share:.4f}, gain={gain}"
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
    print("Done. Refresh your dashboard; HOOD/PNR/MCHP/IPG should now have real Price Paid and P&L.")


if __name__ == "__main__":
    main()
