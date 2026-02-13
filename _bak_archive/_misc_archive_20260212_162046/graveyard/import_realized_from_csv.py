import csv
import sqlite3
from datetime import datetime

LIVE_DB = "live.db"                     # adjust if needed
CSV_PATH = "etrade_realized.csv"        # the file you exported


def ensure_schema(cur):
    # 1) Make sure the table exists with at least core columns
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS realized_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT,
            qty         INTEGER,
            gain        REAL,
            close_date  TEXT
        )
        """
    )

    # 2) Add extra columns if they don't already exist
    for col, decl in [
        ("price_paid", "REAL"),
        ("price_sold", "REAL"),
        ("open_date", "TEXT"),
        ("action", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE realized_trades ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

    # Simple index for faster lookups
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_realized_symbol_dates
        ON realized_trades(symbol, close_date)
        """
    )


def parse_float(s: str) -> float:
    s = (s or "").replace(",", "").strip()
    if s in ("", "--", ".00"):
        return 0.0
    if s.startswith("-.") and len(s) > 2:
        s = "-0" + s[1:]
    elif s.startswith("."):
        s = "0" + s
    return float(s)


def main():
    conn = sqlite3.connect(LIVE_DB)
    cur = conn.cursor()
    ensure_schema(cur)

    with open(CSV_PATH, newline="") as f:
        reader = csv.reader(f)
        in_details = False
        current_symbol = None
        inserted = 0
        skipped = 0

        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue

            first = row[0].strip()

            # Find the start of the TAXABLE G&L DETAILS section
            if first == "TAXABLE G&L DETAILS":
                in_details = True
                current_symbol = None
                continue

            if not in_details:
                continue

            # Skip header row under TAXABLE G&L DETAILS
            if first == "Symbol":
                continue

            # Symbol summary row, e.g. "ZTS", "GILD", "GNRC"
            if first and not first.startswith("Sell"):
                current_symbol = first
                continue

            # Sell detail lines
            if first.startswith("Sell"):
                if not current_symbol:
                    skipped += 1
                    continue

                try:
                    # Columns under the header:
                    # 0: "Sell"
                    # 1: Quantity
                    # 2: Open Date
                    # 3: Cost/Share $
                    # 4: Total Cost $
                    # 5: Close Date
                    # 6: Price/Share $
                    # 7: Proceeds $
                    # 8: Gain $
                    qty_str         = row[1].strip()
                    open_date_str   = row[2].strip()
                    cost_share_str  = row[3]
                    total_cost_str  = row[4]
                    close_date_str  = row[5].strip()
                    price_share_str = row[6]
                    proceeds_str    = row[7]

                    qty        = int(qty_str)
                    cost_total = parse_float(total_cost_str)
                    proceeds   = parse_float(proceeds_str)
                    price_paid = parse_float(cost_share_str)
                    price_sold = parse_float(price_share_str)

                    if price_paid == 0 and qty:
                        price_paid = cost_total / qty

                    gain = proceeds - cost_total

                    open_iso = None
                    if open_date_str and open_date_str != "--":
                        open_iso = datetime.strptime(
                            open_date_str, "%m/%d/%Y"
                        ).date().isoformat()

                    if not close_date_str or close_date_str == "--":
                        skipped += 1
                        continue

                    close_iso = datetime.strptime(
                        close_date_str, "%m/%d/%Y"
                    ).date().isoformat()

                    # NOTE: action='SELL' so we satisfy NOT NULL constraint
                    cur.execute(
                        """
                        INSERT INTO realized_trades
                            (symbol, qty, price_paid, price_sold, gain, open_date, close_date, action)
                        VALUES (?,?,?,?,?,?,?,?)
                        """,
                        (
                            current_symbol,
                            qty,
                            price_paid,
                            price_sold,
                            gain,
                            open_iso,
                            close_iso,
                            "SELL",
                        ),
                    )
                    inserted += 1

                except Exception as e:
                    print("Skip row for", current_symbol, "err:", e, "row:", row)
                    skipped += 1
                    continue

    conn.commit()
    conn.close()
    print(f"Done. Inserted {inserted}, skipped {skipped}.")


if __name__ == "__main__":
    main()
