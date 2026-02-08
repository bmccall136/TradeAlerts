import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\realized_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

pat = re.compile(r"(?s)^def\s+realized_buckets_from_live_db\s*\(.*?\)\s*:\s*.*\Z", re.M)

replacement = r'''def realized_buckets_from_live_db(db_path, now=None, all_start_date=None):
    """
    DB-only realized P&L buckets from sqlite table realized_trades.

    Expects table:
      realized_trades(symbol TEXT, action TEXT, qty REAL, close_date TEXT, gain REAL)

    Returns same *shape* the dashboard expects:
      { "day": {"pnl": x, "pct": 0.0}, "week": {...}, "last_week": {...}, "month": {...}, "all": {...} }

    NOTE: pct is set to 0.0 because DB does not include cost basis here.
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
    week_start = today - _dt.timedelta(days=today.weekday())          # Mon -> today
    last_week_end = week_start - _dt.timedelta(days=1)               # last Sun
    last_week_start = last_week_end - _dt.timedelta(days=6)          # last Mon
    month_start = today.replace(day=1)

    # "all" uses explicit all_start_date if given, else includes everything in table
    all_start = _to_date(all_start_date)  # may be None

    sums = {"day": 0.0, "week": 0.0, "last_week": 0.0, "month": 0.0, "all": 0.0}

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

            # all-time / all since a start date
            if all_start is None or d >= all_start:
                sums["all"] += g

            if d == today:
                sums["day"] += g
            if week_start <= d <= today:
                sums["week"] += g
            if last_week_start <= d <= last_week_end:
                sums["last_week"] += g
            if month_start <= d <= today:
                sums["month"] += g

        def _pack(x):
            return {"pnl": round(float(x), 2), "pct": 0.0}

        return {
            "day": _pack(sums["day"]),
            "week": _pack(sums["week"]),
            "last_week": _pack(sums["last_week"]),
            "month": _pack(sums["month"]),
            "all": _pack(sums["all"]),
        }
    finally:
        con.close()
'''

src2, n = pat.subn(replacement, src, count=1)
if n != 1:
    raise SystemExit(f"ERROR: expected to replace 1 realized_buckets_from_live_db() function, replaced {n}")

p.write_text(src2, encoding="utf-8")
print("OK patched realized_buckets_from_live_db() shape for dashboard")
