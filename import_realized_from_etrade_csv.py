import csv
import sqlite3
import sys
import re
from datetime import datetime

DB_PATH = r"C:\TradeAlerts\live.db"

def _to_float(x):
    if x is None:
        return 0.0
    s = str(x).strip()
    if not s or s == "--":
        return 0.0
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1].strip()
    try:
        return float(s)
    except Exception:
        return 0.0

def _to_iso_date(mdy):
    s = str(mdy).strip()
    if not s or s == "--":
        return None
    try:
        dt = datetime.strptime(s, "%m/%d/%Y")
        return dt.date().isoformat()
    except Exception:
        return None

def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS realized_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        qty REAL,
        close_date TEXT,
        gain REAL,
        total_cost REAL,
        proceeds REAL
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_realized_close_date ON realized_trades(close_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_realized_symbol ON realized_trades(symbol)")
    conn.commit()

def import_etrade_gains_losses(csv_path, db_path=DB_PATH, clear=False):
    inserted = 0
    skipped = 0

    conn = sqlite3.connect(db_path)
    ensure_table(conn)
    cur = conn.cursor()

    if clear:
        cur.execute("DELETE FROM realized_trades")
        conn.commit()

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)

        # 1) Seek to TAXABLE G&L DETAILS header
        header = None
        for row in r:
            if not row:
                continue
            if row[0].strip().upper() == "TAXABLE G&L DETAILS":
                for row2 in r:
                    if row2 and any(c.strip() for c in row2):
                        header = [c.strip() for c in row2]
                        break
                break

        if not header:
            raise SystemExit("Could not find 'TAXABLE G&L DETAILS' section in CSV.")

        def idx(name):
            try:
                return header.index(name)
            except ValueError:
                return None

        idx_symbol = idx("Symbol")
        idx_qty    = idx("Quantity")
        idx_gain   = idx("Gain $")
        idx_def    = idx("Deferred Loss $")  # parsed but ignored for tile P&L
        idx_total_cost = idx("Total Cost $")
        idx_proceeds   = idx("Proceeds $")

        date_indexes = [i for i, h in enumerate(header) if h == "Date"]
        idx_sell_date = date_indexes[1] if len(date_indexes) >= 2 else None

        if idx_qty is None or idx_gain is None or idx_sell_date is None:
            raise SystemExit(f"CSV header missing required columns. Header={header}")

        current_symbol = None

        def get(row, i):
            return row[i] if (i is not None and i < len(row)) else ""

        # 3) Parse rows
        for row in r:
            if not row or not any(c.strip() for c in row):
                continue

            first = (row[0] if len(row) > 0 else "").strip()

            if first.upper() in {"END OF REPORT", "DISCLAIMER", "NON-TAXABLE G&L DETAILS"}:
                break

            # Symbol header line
            if first and not first.upper().startswith("SELL") and not first.startswith("Sell"):
                sym = first
                if re.match(r"^[A-Z0-9.\-]{1,10}$", sym.upper()):
                    current_symbol = sym.upper()
                continue

            # Lot line (SELL)
            if "SELL" in first.upper():
                if not current_symbol:
                    skipped += 1
                    continue

                qty = _to_float(get(row, idx_qty))
                sell_date_iso = _to_iso_date(get(row, idx_sell_date))
                gain = _to_float(get(row, idx_gain))
                _deferred = _to_float(get(row, idx_def)) if idx_def is not None else 0.0  # ignored

                total_cost = _to_float(get(row, idx_total_cost)) if idx_total_cost is not None else 0.0
                proceeds   = _to_float(get(row, idx_proceeds))   if idx_proceeds   is not None else 0.0

                if qty <= 0 or not sell_date_iso:
                    skipped += 1
                    continue

                # ✅ For dashboard realized P&L tiles: broker "Gain $" ONLY
                cur.execute(
                    """
                    INSERT INTO realized_trades (symbol, action, qty, close_date, gain, total_cost, proceeds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (current_symbol, "SELL", float(qty), sell_date_iso, float(gain), float(total_cost), float(proceeds))
                )
                inserted += 1
                continue

            skipped += 1

    conn.commit()
    conn.close()
    return inserted, skipped

def main():
    if len(sys.argv) < 2:
        print("Usage: python import_realized_from_etrade_csv.py <path-to-csv> [db_path] [--clear]")
        sys.exit(2)

    csv_path = sys.argv[1]
    db_path = sys.argv[2] if (len(sys.argv) >= 3 and not sys.argv[2].startswith("--")) else DB_PATH
    clear = "--clear" in sys.argv[2:]

    ins, sk = import_etrade_gains_losses(csv_path, db_path=db_path, clear=clear)
    print(f"Done. Inserted {ins}, skipped {sk}. DB={db_path}")

if __name__ == "__main__":
    main()
