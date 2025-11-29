import sqlite3

DB = r"C:\TradeAlerts\live.db"

# E*TRADE Gains & Losses for 2025-11-26 (your screenshot)
TRADES = [
    # symbol, qty, open_date, close_date, cost_share, price_share, gain, term
    ("STZ",  1.0, "2025-11-25", "2025-11-26 11:46:45", 132.15, 135.80,  3.65, "Short"),
    ("ANET", 1.0, "2025-11-15", "2025-11-26 11:46:47", 134.89, 127.62, -7.27, "Short"),
    ("BBY",  1.0, "2025-11-24", "2025-11-26 13:13:25",  81.13,  81.33,  0.20, "Short"),
    ("KMB",  1.0, "2025-11-25", "2025-11-26 11:47:49", 106.00, 108.93,  2.93, "Short"),
    ("LYV",  1.0, "2025-11-25", "2025-11-26 13:13:57", 128.63, 131.42,  2.79, "Short"),
    ("STT",  1.0, "2025-11-24", "2025-11-26 11:46:49", 115.33, 117.91,  2.58, "Short"),
    ("ALB",  1.0, "2025-11-18", "2025-11-26 11:46:48", 128.13, 126.60, -1.53, "Short"),
]

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    print("Inserting realized trades for 2025-11-26...")
    for sym, qty, open_date, close_date, cost_share, price_share, gain, term in TRADES:
        total_cost = round(cost_share * qty, 2)
        proceeds   = round(price_share * qty, 2)

        print(f"  -> {sym}: qty={qty}, gain={gain}")

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
    print("Done. Check your dashboard Day/Week/Month tiles.")

if __name__ == "__main__":
    main()
