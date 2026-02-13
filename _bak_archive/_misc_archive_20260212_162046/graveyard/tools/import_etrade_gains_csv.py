# import_etrade_gains_csv.py
import os
import sqlite3
from datetime import datetime

LIVE_DB = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")


def _to_float(s):
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except Exception:
        return None


def _to_date(s):
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def import_csv(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = [ln.rstrip("\n") for ln in f]

    # find the “TAXABLE G&L DETAILS” block
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("TAXABLE G&L DETAILS"):
            start = i + 1
            break
    if start is None:
        raise SystemExit("Could not find 'TAXABLE G&L DETAILS' section.")

    conn = sqlite3.connect(LIVE_DB)
    cur = conn.cursor()

    cur.execute("DELETE FROM realized_trades")  # starting fresh for now
    symbol = None

    for ln in lines[start:]:
        if not ln.strip():
            continue
        parts = [p.strip() for p in ln.split(",")]

        # header line within section
        if parts[:3] == ["Symbol", "Quantity", "Date"]:
            continue

        # symbol summary rows (first col is a symbol ticker, not action)
        if parts[0] and parts[0] not in ("Sell", "Buy", "Buy to Cover", "Short", "Cover"):
            symbol = parts[0]
            continue

        # detail rows: action then columns
        if not parts or not parts[0]:
            continue
        action = parts[0]
        if action not in ("Sell", "Buy", "Buy to Cover", "Short", "Cover"):
            continue

        # expected shape:
        # action, qty, open_date, cost_share, total_cost, close_date,
        # price_share, proceeds, gain, deferred, term, lot_selection
        qty = _to_float(parts[1]) if len(parts) > 1 else None
        open_date = _to_date(parts[2]) if len(parts) > 2 else None
        cost_share = _to_float(parts[3]) if len(parts) > 3 else None
        total_cost = _to_float(parts[4]) if len(parts) > 4 else None
        close_date = _to_date(parts[5]) if len(parts) > 5 else None
        price_share = _to_float(parts[6]) if len(parts) > 6 else None
        proceeds = _to_float(parts[7]) if len(parts) > 7 else None
        gain = _to_float(parts[8]) if len(parts) > 8 else None
        term = parts[10] if len(parts) > 10 else None

        if symbol and close_date and gain is not None:
            cur.execute(
                """INSERT INTO realized_trades
                   (symbol, action, qty, open_date, close_date, price_share,
                    proceeds, cost_share, total_cost, gain, term)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol,
                    action,
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
    print(f"✔ Imported into {LIVE_DB}")


if __name__ == "__main__":
    # Pass the CSV path via args or set default
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\TradeAlerts\GainsAndLossesEtrade.csv"
    import_csv(path)
