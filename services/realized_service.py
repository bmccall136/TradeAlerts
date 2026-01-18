# C:\TradeAlerts\services\realized_service.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo

    ETZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ETZ = None  # type: ignore


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS realized_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            qty REAL NOT NULL,
            open_date TEXT,
            close_date TEXT NOT NULL,
            price_paid REAL NOT NULL,
            price_sold REAL NOT NULL,
            gain REAL NOT NULL
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_realized_symbol_close ON realized_trades(symbol, close_date)"
    )
    conn.commit()


def insert_realized_trade(
    db_path: str,
    symbol: str,
    qty: float,
    price_paid: float,
    price_sold: float,
    close_date: str,
    open_date: str | None = None,
    action: str = "SELL",
) -> float:
    symbol = (symbol or "").strip().upper()
    action = (action or "SELL").strip().upper()

    qty_f = float(qty or 0.0)
    pp = float(price_paid or 0.0)
    ps = float(price_sold or 0.0)
    gain = (ps - pp) * qty_f

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        exists = cur.execute(
            """
            SELECT 1
            FROM realized_trades
            WHERE symbol=? AND action=? AND qty=? AND close_date=? AND price_paid=? AND price_sold=?
            LIMIT 1
            """,
            (symbol, action, float(qty_f), close_date, float(pp), float(ps)),
        ).fetchone()
        if exists:
            return float(gain)

        cur.execute(
            """
            INSERT INTO realized_trades
              (symbol, action, qty, open_date, close_date, price_paid, price_sold, gain)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (symbol, action, float(qty_f), open_date, close_date, float(pp), float(ps), float(gain)),
        )
        conn.commit()
    finally:
        conn.close()

    return float(gain)


def _parse_close_dt(x: Any) -> Optional[datetime]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace("T", " ")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _table_cols(cur: sqlite3.Cursor, table: str) -> set[str]:
    cols = set()
    for r in cur.execute(f"PRAGMA table_info({table})").fetchall():
        cols.add(str(r[1]))
    return cols


def realized_buckets_from_live_db(db_path: str, denom_value: float = 0.0) -> Dict[str, Dict[str, float]]:
    """
    Realized P&L buckets from local live.db realized_trades.

    CRITICAL:
    - We IGNORE rows that have no usable cost basis (total_cost == 0 AND price_paid/cost_share missing/0),
      because those rows create fake huge gains (gain == proceeds).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cols = _table_cols(cur, "realized_trades")

        if "close_date" not in cols:
            return {
                "day": {"pnl": 0.0, "pct": 0.0},
                "week": {"pnl": 0.0, "pct": 0.0},
                "last_week": {"pnl": 0.0, "pct": 0.0},
                "month": {"pnl": 0.0, "pct": 0.0},
                "all": {"pnl": 0.0, "pct": 0.0},
            }

        where = """
            close_date IS NOT NULL
            AND symbol <> 'TEST'
            AND (
                  action IS NULL
                  OR TRIM(action) = ''
                  OR UPPER(action) IN ('SELL','SOLD')
                )
        """

        sel = ["close_date", "symbol"]
        for c in ("action", "qty", "gain", "total_cost", "proceeds", "price_paid", "price_sold", "cost_share"):
            if c in cols:
                sel.append(c)

        rows = cur.execute(
            f"SELECT {', '.join(sel)} FROM realized_trades WHERE {where} ORDER BY close_date DESC"
        ).fetchall()
    finally:
        conn.close()

    now = datetime.now(ETZ) if ETZ is not None else datetime.now()
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week0 = today0 - timedelta(days=today0.weekday())  # Monday
    month0 = today0.replace(day=1)
    last_week_end = week0
    last_week_start = last_week_end - timedelta(days=7)

    buckets = {
        "day": {"pnl": 0.0, "cost": 0.0},
        "week": {"pnl": 0.0, "cost": 0.0},
        "last_week": {"pnl": 0.0, "cost": 0.0},
        "month": {"pnl": 0.0, "cost": 0.0},
        "all": {"pnl": 0.0, "cost": 0.0},
    }

    has_total_cost = "total_cost" in cols

    for r in rows:
        dt_close = _parse_close_dt(r["close_date"])
        if dt_close is None:
            continue
        if dt_close.tzinfo is None and ETZ is not None:
            dt_close = dt_close.replace(tzinfo=ETZ)

        qty = _safe_float(r["qty"]) if "qty" in cols else 0.0
        qty = float(qty or 0.0)

        proceeds = _safe_float(r["proceeds"]) if "proceeds" in cols else None
        total_cost = _safe_float(r["total_cost"]) if "total_cost" in cols else None
        gain = _safe_float(r["gain"]) if "gain" in cols else 0.0
        gain = float(gain or 0.0)

        price_paid = _safe_float(r["price_paid"]) if "price_paid" in cols else None
        cost_share = _safe_float(r["cost_share"]) if "cost_share" in cols else None
        price_sold = _safe_float(r["price_sold"]) if "price_sold" in cols else None

        # ---- compute cost if missing/zero
        tc = float(total_cost or 0.0)
        if tc == 0.0:
            if price_paid is not None and float(price_paid) > 0.0 and qty > 0:
                tc = qty * float(price_paid)
            elif cost_share is not None and float(cost_share) > 0.0 and qty > 0:
                tc = qty * float(cost_share)

        # ---- compute proceeds if missing/zero
        pr = float(proceeds or 0.0)
        if pr == 0.0 and price_sold is not None and float(price_sold) > 0.0 and qty > 0:
            pr = qty * float(price_sold)

        # ---- reject corrupt rows with no real cost basis
        # If we still have tc==0 but proceeds exists, the row is unusable (this is your inflated case)
        if tc == 0.0 and pr != 0.0:
            continue

        # ---- compute pnl
        if pr != 0.0 and tc != 0.0:
            pnl = pr - tc
        else:
            # fallback only if it doesn't look like "gain == proceeds"
            pnl = gain

        # all
        buckets["all"]["pnl"] += pnl
        buckets["all"]["cost"] += tc if has_total_cost else 0.0

        # month/week/day windows
        if dt_close >= month0:
            buckets["month"]["pnl"] += pnl
            buckets["month"]["cost"] += tc if has_total_cost else 0.0

        if dt_close >= week0:
            buckets["week"]["pnl"] += pnl
            buckets["week"]["cost"] += tc if has_total_cost else 0.0

        if last_week_start <= dt_close < last_week_end:
            buckets["last_week"]["pnl"] += pnl
            buckets["last_week"]["cost"] += tc if has_total_cost else 0.0

        if dt_close >= today0:
            buckets["day"]["pnl"] += pnl
            buckets["day"]["cost"] += tc if has_total_cost else 0.0

    def pct(pnl: float, cost_sum: float) -> float:
        try:
            if denom_value and float(denom_value) > 0:
                return round((float(pnl) / float(denom_value)) * 100.0, 2)
            if cost_sum and float(cost_sum) != 0.0:
                return round((float(pnl) / float(cost_sum)) * 100.0, 2)
        except Exception:
            pass
        return 0.0

    out: Dict[str, Dict[str, float]] = {}
    for k in ("day", "week", "last_week", "month", "all"):
        pnl_v = float(buckets[k]["pnl"])
        cost_v = float(buckets[k]["cost"])
        out[k] = {"pnl": round(pnl_v, 2), "pct": pct(pnl_v, cost_v)}

    return out
