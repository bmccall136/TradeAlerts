# services/realized_service.py
from __future__ import annotations

import sqlite3
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


ETZ = ZoneInfo("America/New_York")


def _parse_dt(s: str | None) -> Optional[dt.datetime]:
    """
    Accepts:
      - 'YYYY-MM-DD HH:MM:SS'
      - 'YYYY-MM-DDTHH:MM:SS'
      - 'YYYY-MM-DD' (treated as midnight)
    Returns timezone-aware ET datetime, or None.
    """
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None

    s = s.replace("T", " ")
    try:
        if len(s) == 10:
            d = dt.datetime.strptime(s, "%Y-%m-%d")
            return d.replace(tzinfo=ETZ)
        d = dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        return d.replace(tzinfo=ETZ)
    except Exception:
        return None


def _start_of_day(now_et: dt.datetime) -> dt.datetime:
    return now_et.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week(now_et: dt.datetime) -> dt.datetime:
    # Monday 00:00 ET
    d0 = _start_of_day(now_et)
    return d0 - dt.timedelta(days=d0.weekday())


def _start_of_last_week(now_et: dt.datetime) -> dt.datetime:
    # Previous Monday 00:00 ET
    return _start_of_week(now_et) - dt.timedelta(days=7)


def _start_of_month(now_et: dt.datetime) -> dt.datetime:
    # 1st of month 00:00 ET
    d0 = _start_of_day(now_et)
    return d0.replace(day=1)


def _sum_gain(conn: sqlite3.Connection, start: Optional[dt.datetime], end: Optional[dt.datetime]) -> float:
    """
    Sum realized gains from realized_trades.
    Uses gain when present; else proceeds - total_cost.
    Filters:
      - symbol <> 'TEST'
      - action NULL/blank or SELL/SOLD
      - close_date not null
    Date filtering:
      - Uses close_date string compare after normalizing 'T' -> ' '.
      - We compare by 'YYYY-MM-DD HH:MM:SS' string ranges.
    """
    cur = conn.cursor()

    where = [
        "symbol <> 'TEST'",
        "close_date IS NOT NULL",
        "("
        " action IS NULL OR TRIM(action) = '' OR UPPER(action) IN ('SELL','SOLD')"
        ")",
    ]

    params: list[Any] = []

    if start is not None:
        where.append("REPLACE(substr(close_date,1,19),'T',' ') >= ?")
        params.append(start.strftime("%Y-%m-%d %H:%M:%S"))
    if end is not None:
        where.append("REPLACE(substr(close_date,1,19),'T',' ') <= ?")
        params.append(end.strftime("%Y-%m-%d %H:%M:%S"))

    sql = f"""
    SELECT
      COALESCE(
        SUM(
          CASE
            WHEN gain IS NOT NULL THEN CAST(gain AS REAL)
            ELSE (CAST(COALESCE(proceeds,0) AS REAL) - CAST(COALESCE(total_cost,0) AS REAL))
          END
        ),
        0
      ) AS s
    FROM realized_trades
    WHERE {" AND ".join(where)}
    """
    row = cur.execute(sql, params).fetchone()
    try:
        return float(row[0] or 0.0)
    except Exception:
        return 0.0


def realized_buckets_from_live_db(db_path: str, denom_value: float | None = None) -> Dict[str, Dict[str, float]]:
    """
    Returns:
      {
        'day': {'pnl': x, 'pct': y},
        'week': {'pnl': x, 'pct': y},
        'last_week': {'pnl': x, 'pct': y},
        'month': {'pnl': x, 'pct': y},
        'all': {'pnl': x, 'pct': y},
      }

    denom_value is optional (for pct); if not provided or <=0, pct is 0.0.
    """
    now_et = dt.datetime.now(ETZ)
    day0 = _start_of_day(now_et)
    week0 = _start_of_week(now_et)
    last_week0 = _start_of_last_week(now_et)
    month0 = _start_of_month(now_et)

    with sqlite3.connect(db_path) as conn:
        day_pnl = _sum_gain(conn, day0, None)
        week_pnl = _sum_gain(conn, week0, None)
        last_week_pnl = _sum_gain(conn, last_week0, week0 - dt.timedelta(seconds=1))
        month_pnl = _sum_gain(conn, month0, None)
        all_pnl = _sum_gain(conn, None, None)

    denom = float(denom_value or 0.0)
    def pct(x: float) -> float:
        if denom <= 0:
            return 0.0
        return (float(x) / denom) * 100.0

    return {
        "day": {"pnl": float(day_pnl), "pct": float(pct(day_pnl))},
        "week": {"pnl": float(week_pnl), "pct": float(pct(week_pnl))},
        "last_week": {"pnl": float(last_week_pnl), "pct": float(pct(last_week_pnl))},
        "month": {"pnl": float(month_pnl), "pct": float(pct(month_pnl))},
        "all": {"pnl": float(all_pnl), "pct": float(pct(all_pnl))},
    }
