# add_realized_trade.py
#
# Helper to manually insert a realized trade into live.db so
# Day / Week / Month / All buckets can see it.

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# --- Config ---
LIVE_DB = r"C:\TradeAlerts\live.db"   # adjust if needed

ET = ZoneInfo("America/New_York")


def main():
    db_path = Path(LIVE_DB)
    if not db_path.exists():
        raise SystemExit(f"ERROR: live.db not found at {db_path}")

    print(f"Using DB: {db_path}")

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    # Show schema so we can see what columns exist
    cur.execute("PRAGMA table_info(realized_trades)")
    schema_rows = cur.fetchall()
    if not schema_rows:
        raise SystemExit("ERROR: Table realized_trades not found in live.db")

    print("\n=== realized_trades schema ===")
    for cid, name, ctype, notnull, dflt, pk in schema_rows:
        print(f"{cid:2d}: {name:15s} {ctype:10s} NOTNULL={notnull} PK={pk} DEFAULT={dflt}")
    print("================================\n")

    cols = [r[1] for r in schema_rows]

    # --- Collect inputs from you ---
    symbol = input("Symbol (e.g. MRNA): ").strip().upper()
    if not symbol:
        raise SystemExit("Symbol is required.")

    try:
        qty = float(input("Quantity sold (e.g. 1): ").strip())
    except ValueError:
        raise SystemExit("Invalid quantity.")

    try:
        price_paid = float(input("Avg price PAID per share (your cost basis, e.g. 90.00): ").strip())
        sell_price = float(input("Sell price per share (e.g. 95.00): ").strip())
    except ValueError:
        raise SystemExit("Invalid price input.")

    default_dt = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S")
    close_date = input(
        f"Close date/time [{default_dt}] (YYYY-MM-DD HH:MM:SS ET, Enter for now): "
    ).strip()
    if not close_date:
        close_date = default_dt

    basis_total = round(qty * price_paid, 2)
    proceeds_total = round(qty * sell_price, 2)
    gain = round(proceeds_total - basis_total, 2)

    print("\nComputed values:")
    print(f"  Basis total    = {basis_total:.2f}")
    print(f"  Proceeds total = {proceeds_total:.2f}")
    print(f"  GAIN (P&L)     = {gain:.2f}")
    print(f"  Close date     = {close_date}")

    confirm = input("\nInsert this trade into realized_trades? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # --- Build column map based on what actually exists ---
    col_map = {}

    # required fields in your schema:
    # symbol (TEXT, NOT NULL)
    # action (TEXT, NOT NULL)
    # qty    (REAL, NOT NULL)
    # close_date (TEXT, NOT NULL)

    if "symbol" in cols:
        col_map["symbol"] = symbol

    # hard-code action as SELL for this helper
    if "action" in cols:
        col_map["action"] = "SELL"

    # qty / shares
    if "qty" in cols:
        col_map["qty"] = qty
    elif "shares" in cols:
        col_map["shares"] = qty
    elif "quantity" in cols:
        col_map["quantity"] = qty

    # close_date (required for buckets)
    if "close_date" in cols:
        col_map["close_date"] = close_date
    elif "sell_date" in cols:
        col_map["sell_date"] = close_date

    # proceeds
    if "proceeds" in cols:
        col_map["proceeds"] = proceeds_total
    elif "amount" in cols:
        col_map["amount"] = proceeds_total

    # per-share price & cost if present
    if "price_share" in cols:
        col_map["price_share"] = sell_price
    if "cost_share" in cols:
        col_map["cost_share"] = price_paid

    # total_cost / basis if present
    if "total_cost" in cols:
        col_map["total_cost"] = basis_total
    elif "basis" in cols:
        col_map["basis"] = basis_total
    elif "cost_basis" in cols:
        col_map["cost_basis"] = basis_total

    # gain (required for buckets)
    if "gain" in cols:
        col_map["gain"] = gain
    else:
        print("WARNING: 'gain' column not found; trade will insert without gain, buckets may ignore it.")

    if not col_map:
        raise SystemExit("ERROR: No known columns to insert. Check schema above.")

    # Build and execute INSERT
    col_names = ", ".join(col_map.keys())
    placeholders = ", ".join(["?"] * len(col_map))
    values = list(col_map.values())

    sql = f"INSERT INTO realized_trades ({col_names}) VALUES ({placeholders})"
    print("\nSQL:", sql)
    print("Vals:", values)

    cur.execute(sql, values)
    con.commit()
    con.close()

    print("\n✅ Inserted manual realized trade row into realized_trades.")
    print("Now refresh your dashboard and check the Day / Week buckets.")


if __name__ == "__main__":
    main()
