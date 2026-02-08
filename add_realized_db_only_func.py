from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\realized_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

if "def realized_buckets_from_live_db" in src:
    raise SystemExit("ERROR: realized_buckets_from_live_db already exists in realized_service.py (won't duplicate)")

append_code = r'''

def realized_buckets_from_live_db(db_path, now=None):
    """
    DB-only realized P&L buckets from sqlite table realized_trades.

    Expects table:
      realized_trades(symbol TEXT, action TEXT, qty REAL, close_date TEXT, gain REAL)

    Buckets returned are true:
      - day (today)
      - week-to-date (Mon -> today)
      - month-to-date (1st -> today)
      - year-to-date (Jan 1 -> today)
    """
    import sqlite3
    import datetime as _dt

    def _to_date(v):
        if v is None:
            return None
        if isinstance(v, _dt.date) and not isinstance(v, _dt.datetime):
            return v
        s = str(v).strip()
        if not s:
            return None
        s10 = s[:10]  # accept YYYY-MM-DD or ISO string
        try:
            return _dt.date.fromisoformat(s10)
        except Exception:
            return None

    today = _to_date(now) or _dt.datetime.now().date()
    week_start = today - _dt.timedelta(days=today.weekday())  # Monday
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    buckets = {"day": 0.0, "week": 0.0, "month": 0.0, "year": 0.0}

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        rows = cur.execute(
            "SELECT close_date, gain FROM realized_trades WHERE gain IS NOT NULL"
        ).fetchall()

        for close_date, gain in rows:
            d = _to_date(close_date)
            if d is None:
                continue
            try:
                g = float(gain or 0.0)
            except Exception:
                continue

            if d == today:
                buckets["day"] += g
            if week_start <= d <= today:
                buckets["week"] += g
            if month_start <= d <= today:
                buckets["month"] += g
            if year_start <= d <= today:
                buckets["year"] += g

        return buckets
    finally:
        con.close()
'''

# Append with a newline boundary
src2 = src.rstrip() + "\n" + append_code.lstrip("\n")
p.write_text(src2, encoding="utf-8")
print("OK added realized_buckets_from_live_db() (DB-only) to realized_service.py")
