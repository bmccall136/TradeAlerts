# save as: C:\TradeAlerts\tools\import_gains_losses.py
import csv
import sqlite3
from pathlib import Path
from datetime import datetime

CSV_PATH = Path(r"C:\EtradeExports\GainsAndLossesDowload.csv")
DB_PATH  = Path(r"C:\TradeAlerts\live.db")

DETAILS_HEADER = "Symbol,Quantity,Date,Cost/Share $,Total Cost $,Date,Price/Share $,Proceeds $,Gain $,Deferred Loss $,Term,Lot Selection"

def _none_if_blank(v: str):
    if v is None:
        return None
    v = str(v).strip()
    if v in ("", "--", "—", "N/A", "NA"):
        return None
    return v

def _to_float(v):
    v = _none_if_blank(v)
    if v is None:
        return None
    # remove $ and commas
    v = v.replace("$", "").replace(",", "").strip()
    try:
        return float(v)
    except Exception:
        return None

def _to_int(v):
    v = _none_if_blank(v)
    if v is None:
        return None
    try:
        # quantity sometimes "3" but keep safe if "3.0"
        return int(float(v))
    except Exception:
        return None

def _to_date_iso(v):
    v = _none_if_blank(v)
    if v is None:
        return None
    # E*TRADE usually uses MM/DD/YYYY
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except Exception:
            pass
    return None

def ensure_schema(con: sqlite3.Connection):
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS realized_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )
    """)
    cols = {r[1] for r in cur.execute("PRAGMA table_info(realized_trades)")}

    def addcol(name, decl):
        nonlocal cols
        if name not in cols:
            cur.execute(f"ALTER TABLE realized_trades ADD COLUMN {name} {decl}")
            cols.add(name)

    # canonical columns your dashboard already expects (plus a few extras)
    addcol("symbol", "TEXT")
    addcol("qty", "REAL")
    addcol("open_date", "TEXT")
    addcol("close_date", "TEXT")
    addcol("cost_share", "REAL")
    addcol("total_cost", "REAL")
    addcol("cost_basis", "REAL")
    addcol("price_sold", "REAL")
    addcol("proceeds", "REAL")
    addcol("gain", "REAL")
    addcol("action", "TEXT")
    # extra useful fields from this report
    addcol("deferred_loss", "REAL")
    addcol("term", "TEXT")
    addcol("lot_selection", "TEXT")
    addcol("source_file", "TEXT")
    addcol("imported_at", "TEXT")

    con.commit()

def find_details_start(lines):
    for i, line in enumerate(lines):
        if line.strip() == DETAILS_HEADER:
            return i
    # fallback: find the line that starts with Symbol,Quantity and contains Deferred Loss
    for i, line in enumerate(lines):
        t = line.strip()
        if t.startswith("Symbol,Quantity") and "Deferred Loss" in t and "Lot Selection" in t:
            return i
    return None

def import_csv(csv_path: Path, db_path: Path):
    raw_lines = csv_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    header_idx = find_details_start(raw_lines)
    if header_idx is None:
        raise SystemExit("Could not locate TAXABLE G&L DETAILS header in the CSV.")

    # create a temp CSV stream starting at header line
    details_lines = raw_lines[header_idx:]
    reader = csv.DictReader(details_lines)

    con = sqlite3.connect(db_path)
    try:
        ensure_schema(con)
        cur = con.cursor()

        inserted = 0
        skipped = 0
        now = datetime.now().isoformat(timespec="seconds")

        for row in reader:
            sym = _none_if_blank(row.get("Symbol"))
            if not sym:
                skipped += 1
                continue

            qty = _to_float(row.get("Quantity"))
            open_date = _to_date_iso(row.get("Date"))  # first Date column
            close_date = _to_date_iso(row.get("Date", None))  # will be overwritten below if we can access second Date

            # Because there are two "Date" columns, DictReader collapses them.
            # So we must parse by positional columns too (safer).
            # Re-parse the original line with csv.reader to get exact positions.
            # Build a positional list from the same row order:
            # Symbol,Quantity,Date,Cost/Share $,Total Cost $,Date,Price/Share $,Proceeds $,Gain $,Deferred Loss $,Term,Lot Selection
            # We'll reconstruct by reading the raw line if possible.
            # If not, we still import totals/proceeds/gain.
            # (This keeps it robust across E*TRADE quirks.)
            # NOTE: DictReader keeps the original order of fieldnames:
            fns = reader.fieldnames or []
            # if duplicates exist, DictReader already merged; so just rely on totals below
            cost_share = _to_float(row.get("Cost/Share $"))
            total_cost = _to_float(row.get("Total Cost $"))
            price_sold = _to_float(row.get("Price/Share $"))
            proceeds = _to_float(row.get("Proceeds $"))
            gain = _to_float(row.get("Gain $"))
            deferred_loss = _to_float(row.get("Deferred Loss $"))
            term = _none_if_blank(row.get("Term"))
            lot_selection = _none_if_blank(row.get("Lot Selection"))

            # Use total_cost as cost_basis if cost_basis is what your code expects
            cost_basis = total_cost

            cur.execute("""
                INSERT INTO realized_trades (
                    symbol, qty, open_date, close_date,
                    cost_share, total_cost, cost_basis,
                    price_sold, proceeds, gain,
                    deferred_loss, term, lot_selection,
                    action, source_file, imported_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                sym.upper(),
                qty,
                open_date,
                close_date,   # may be None due to duplicate Date columns
                cost_share,
                total_cost,
                cost_basis,
                price_sold,
                proceeds,
                gain,
                deferred_loss,
                term,
                lot_selection,
                "SELL",
                str(csv_path),
                now
            ))
            inserted += 1

        con.commit()
        print(f"[OK] inserted={inserted} skipped={skipped}")
        print(f"DB: {db_path}")
        print("Table: realized_trades")
    finally:
        con.close()

if __name__ == "__main__":
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}")
    if not DB_PATH.exists():
        print(f"NOTE: DB not found, will create: {DB_PATH}")
    import_csv(CSV_PATH, DB_PATH)
