# --- drop-in replacement ---
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

def realized_buckets_from_live_db(db_path: str,
                                  since: str | None = None,
                                  start_cash: float | None = None) -> dict | None:
    """
    Build realized P&L buckets (week, last_week, month, all) from live.db.

    - Auto-detects schema:
        * new: columns 'time' (ISO text), 'pnl'
        * old: columns 'close_date' (ISO text), 'gain'
    - Only includes rows on/after `since` (defaults to env PROJECT_START).
    - Percent is computed vs START_CASH (env) so your 'All' matches the headline.
    """

    since = since or os.environ.get("PROJECT_START", "2025-08-22")
    try:
        start_cash = float(start_cash if start_cash is not None
                           else os.environ.get("START_CASH", "392.67"))
    except Exception:
        start_cash = 0.0

    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
    except Exception:
        return None

    # ---- detect columns ----
    try:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(realized_trades)")}
    except Exception:
        cols = set()

    # pick time / pnl columns based on what exists
    time_col = "time"        if "time" in cols else ("close_date" if "close_date" in cols else None)
    pnl_col  = "pnl"         if "pnl"  in cols else ("gain"       if "gain"       in cols else None)

    if not time_col or not pnl_col:
        # table missing or unknown schema
        return {"week": {"pnl": 0.0, "pct": 0.0},
                "last_week": {"pnl": 0.0, "pct": 0.0},
                "month": {"pnl": 0.0, "pct": 0.0},
                "all": {"pnl": 0.0, "pct": 0.0}}

    # ---- boundaries in ET ----
    now = datetime.now(ET)
    week_start      = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = week_start - timedelta(days=7)
    last_week_end   = week_start
    month_start     = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ---- helpers ----
    def _sum_between(start_dt: datetime, end_dt: datetime | None):
        q = f"SELECT COALESCE(SUM({pnl_col}),0.0) FROM realized_trades " \
            f"WHERE date({time_col}) >= date(?) AND {time_col} >= ?"
        args = [since, start_dt.isoformat()]
        if end_dt is not None:
            q += f" AND {time_col} < ?"
            args.append(end_dt.isoformat())
        (val,) = con.execute(q, args).fetchone()
        return float(val or 0.0)

    def _sum_all_since():
        q = f"SELECT COALESCE(SUM({pnl_col}),0.0) FROM realized_trades " \
            f"WHERE date({time_col}) >= date(?)"
        (val,) = con.execute(q, (since,)).fetchone()
        return float(val or 0.0)

    wk   = _sum_between(week_start, None)
    lwk  = _sum_between(last_week_start, last_week_end)
    mon  = _sum_between(month_start, None)
    tall = _sum_all_since()

    def _fmt(pnl: float, basis: float | None):
        pnl = round(pnl, 2)
        pct = round((pnl / basis * 100.0), 2) if basis and basis > 0 else 0.0
        return {"pnl": pnl, "pct": pct}

    return {
        "week":      _fmt(wk,  start_cash),
        "last_week": _fmt(lwk, start_cash),
        "month":     _fmt(mon, start_cash),
        "all":       _fmt(tall, start_cash),
    }
# --- end drop-in ---

