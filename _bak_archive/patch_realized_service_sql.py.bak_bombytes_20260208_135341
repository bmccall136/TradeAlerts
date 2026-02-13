from pathlib import Path
from datetime import datetime
import re

p = Path(r"C:\TradeAlerts\services\realized_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

pat = re.compile(r"(?ms)^def\s+realized_buckets_from_live_db\b.*?(?=^def\b|^class\b|\Z)")

replacement = r'''def realized_buckets_from_live_db(db_path, now=None, all_start_date=None):
    """
    DB-only realized P&L buckets from sqlite table realized_trades.

    Returns the shape dashboard expects:
      {day:{pnl,pct}, week:{pnl,pct}, last_week:{pnl,pct}, month:{pnl,pct}, all:{pnl,pct}}
    pct is 0.0 (no cost basis in realized_trades).
    """
    import sqlite3
    import datetime as _dt

    # Use ET date boundaries; but because close_date is stored as YYYY-MM-DD,
    # string comparisons work safely if we normalize to 10 chars.
    if now is None:
        today = _dt.date.today()
    else:
        # accept date/datetime/iso string
        if isinstance(now, _dt.datetime):
            today = now.date()
        elif isinstance(now, _dt.date):
            today = now
        else:
            s = str(now).strip()[:10]
            try:
                today = _dt.date.fromisoformat(s)
            except Exception:
                today = _dt.date.today()

    week_start = today - _dt.timedelta(days=today.weekday())          # Mon
    last_week_end = week_start - _dt.timedelta(days=1)               # Sun
    last_week_start = last_week_end - _dt.timedelta(days=6)          # Mon
    month_start = today.replace(day=1)

    all_start = None
    if all_start_date is not None:
        if isinstance(all_start_date, _dt.datetime):
            all_start = all_start_date.date()
        elif isinstance(all_start_date, _dt.date):
            all_start = all_start_date
        else:
            s = str(all_start_date).strip()[:10]
            try:
                all_start = _dt.date.fromisoformat(s)
            except Exception:
                all_start = None

    def _pack(x):
        try:
            x = float(x or 0.0)
        except Exception:
            x = 0.0
        return {"pnl": round(x, 2), "pct": 0.0}

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()

        # Normalize close_date to YYYY-MM-DD (first 10 chars)
        # IMPORTANT: use COALESCE(SUM(...),0) so empty buckets are 0 not None.
        day = cur.execute(
            "SELECT COALESCE(SUM(gain),0) FROM realized_trades WHERE substr(close_date,1,10)=?",
            (today.isoformat(),)
        ).fetchone()[0]

        week = cur.execute(
            "SELECT COALESCE(SUM(gain),0) FROM realized_trades WHERE substr(close_date,1,10) BETWEEN ? AND ?",
            (week_start.isoformat(), today.isoformat())
        ).fetchone()[0]

        last_week = cur.execute(
            "SELECT COALESCE(SUM(gain),0) FROM realized_trades WHERE substr(close_date,1,10) BETWEEN ? AND ?",
            (last_week_start.isoformat(), last_week_end.isoformat())
        ).fetchone()[0]

        month = cur.execute(
            "SELECT COALESCE(SUM(gain),0) FROM realized_trades WHERE substr(close_date,1,10) BETWEEN ? AND ?",
            (month_start.isoformat(), today.isoformat())
        ).fetchone()[0]

        if all_start is None:
            allv = cur.execute(
                "SELECT COALESCE(SUM(gain),0) FROM realized_trades"
            ).fetchone()[0]
        else:
            allv = cur.execute(
                "SELECT COALESCE(SUM(gain),0) FROM realized_trades WHERE substr(close_date,1,10) >= ?",
                (all_start.isoformat(),)
            ).fetchone()[0]

        return {
            "day": _pack(day),
            "week": _pack(week),
            "last_week": _pack(last_week),
            "month": _pack(month),
            "all": _pack(allv),
        }
    finally:
        con.close()
'''

src2, n = pat.subn(replacement, src, count=1)
if n != 1:
    raise SystemExit(f"ERROR: expected to replace 1 realized_buckets_from_live_db() block, replaced {n}")

p.write_text(src2, encoding="utf-8")
print("OK: patched realized_buckets_from_live_db() to SQL-based buckets")
