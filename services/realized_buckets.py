# services/realized_buckets.py
import os
import sqlite3
from datetime import UTC, datetime, timedelta

# Fixed starting bankroll (you can override via env START_CASH)
START_CASH = float(os.environ.get("START_CASH", "392.76"))


def _d(dt):
    return dt.strftime("%Y-%m-%d")


def realized_buckets_from_live_db(db_path: str) -> dict | None:
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
    except Exception:
        return None

    def sum_gain(start_d=None, end_d=None) -> float:
        q = "SELECT COALESCE(SUM(gain),0.0) FROM realized_trades WHERE gain IS NOT NULL"
        params = []
        if start_d is not None:
            q += " AND date(close_date) >= date(?)"
            params.append(start_d)
        if end_d is not None:
            q += " AND date(close_date) <  date(?)"
            params.append(end_d)
        return float(con.execute(q, params).fetchone()[0] or 0.0)

    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_monday = monday - timedelta(days=7)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    md, lmd, fdom = _d(monday), _d(last_monday), _d(first_of_month)

    def bucket(start_d=None, end_d=None):
        pnl = sum_gain(start_d, end_d)
        pct = (pnl / START_CASH * 100.0) if START_CASH > 0 else 0.0  # <-- YOUR WAY
        return {"pnl": pnl, "pct": pct}

    return {
        "week": bucket(md, None),
        "last_week": bucket(lmd, md),
        "month": bucket(fdom, None),
        "all": bucket(None, None),
    }
