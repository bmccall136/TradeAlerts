
import sqlite3
from typing import Any, Dict, Iterable, Optional

def _norm_side(v: Any) -> str:
    s = ("" if v is None else str(v)).strip().upper()
    if s in ("BUY","SELL"):
        return s
    if s in ("B","BOT"):
        return "BUY"
    if s in ("S","SLD","SOLD"):
        return "SELL"
    return s

def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        return int(float(v))
    except Exception:
        return None

def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def ensure_trades_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_dedupe "
        "ON trades(ts_utc, symbol, action, qty, price)"
    )
    con.commit()

def persist_trades(db_path: str, rows):
    """
    Persist UI 'Recent Trades' rows into live.db.trades.

    Accepts rows shaped like /live/data payload:
      keys: time, time_utc, time_ms, action, symbol, qty, price, price_paid, pl, pl_pct, amount

    Writes into trades table with schema-adaptive columns.
    Dedupes by (symbol, action, ts_et, qty, price).
    """
    if not rows:
        return 0

    import sqlite3

    def _norm_sym(x):
        try:
            return str(x or "").upper().strip()
        except Exception:
            return ""

    def _to_float(x):
        try:
            if x is None or x == "":
                return None
            return float(x)
        except Exception:
            return None

    def _to_int(x):
        try:
            if x is None or x == "":
                return None
            return int(x)
        except Exception:
            return None

    def _parse_epoch_from_ms(ms):
        try:
            if ms is None:
                return None
            return int(int(ms) / 1000)
        except Exception:
            return None

    con = sqlite3.connect(db_path, timeout=5)
    cur = con.cursor()

    # discover schema
    cols = cur.execute("PRAGMA table_info(trades);").fetchall()
    col_names = [c[1] for c in cols]
    col_types = {c[1]: (c[2] or "").upper() for c in cols}

    has = set(col_names)

    # determine ts_utc storage preference
    ts_utc_type = col_types.get("ts_utc", "")
    ts_utc_wants_int = any(k in ts_utc_type for k in ("INT", "REAL", "NUM"))

    # build insert columns based on what exists
    base_cols = []
    for c in ["ts_utc","ts_et","symbol","name","qty","price","price_paid","pnl","pnl_pct","action"]:
        if c in has:
            base_cols.append(c)

    if not base_cols:
        con.close()
        raise RuntimeError("trades table has no expected columns; found: " + ",".join(col_names))

    qmarks = ",".join(["?"] * len(base_cols))
    sql = f"INSERT INTO trades ({','.join(base_cols)}) VALUES ({qmarks})"

    # dedupe query (best-effort on available columns)
    dedupe_cols = [c for c in ["symbol","action","ts_et","qty","price"] if c in has]
    if len(dedupe_cols) >= 3:
        where = " AND ".join([f"{c}=?" for c in dedupe_cols])
        sql_exists = f"SELECT 1 FROM trades WHERE {where} LIMIT 1"
    else:
        sql_exists = None

    inserted = 0

    for r in rows:
        if not isinstance(r, dict):
            continue

        sym = _norm_sym(r.get("symbol"))
        if not sym:
            continue

        action = (r.get("action") or r.get("side") or "").upper().strip() or None
        qty = _to_float(r.get("qty"))
        price = _to_float(r.get("price"))
        price_paid = _to_float(r.get("price_paid"))

        # payload gives 'time' as ET string (already what UI shows)
        ts_et = r.get("time") or r.get("ts_et") or r.get("time_et") or None

        # derive ts_utc: prefer epoch from time_ms; else use time_utc string; else fall back to ts_et
        epoch = _parse_epoch_from_ms(r.get("time_ms"))
        t_utc_str = r.get("time_utc") or r.get("ts_utc") or None
        if ts_utc_wants_int:
            ts_utc = epoch if epoch is not None else None
        else:
            ts_utc = t_utc_str or ts_et

        pnl = _to_float(r.get("pl") if "pl" in r else r.get("pnl"))
        pnl_pct = _to_float(r.get("pl_pct") if "pl_pct" in r else r.get("pnl_pct"))

        name = r.get("name") or None

        # dedupe
        if sql_exists:
            probe_vals = []
            for c in dedupe_cols:
                if c == "symbol": probe_vals.append(sym)
                elif c == "action": probe_vals.append(action)
                elif c == "ts_et": probe_vals.append(ts_et)
                elif c == "qty": probe_vals.append(qty)
                elif c == "price": probe_vals.append(price)
                else: probe_vals.append(None)
            try:
                if cur.execute(sql_exists, probe_vals).fetchone():
                    continue
            except Exception:
                # if dedupe probe fails, just attempt insert
                pass

        row_vals = []
        for c in base_cols:
            if c == "ts_utc": row_vals.append(ts_utc)
            elif c == "ts_et": row_vals.append(ts_et)
            elif c == "symbol": row_vals.append(sym)
            elif c == "name": row_vals.append(name)
            elif c == "qty": row_vals.append(qty)
            elif c == "price": row_vals.append(price)
            elif c == "price_paid": row_vals.append(price_paid)
            elif c == "pnl": row_vals.append(pnl)
            elif c == "pnl_pct": row_vals.append(pnl_pct)
            elif c == "action": row_vals.append(action)
            else: row_vals.append(None)

        try:
            cur.execute(sql, row_vals)
            inserted += 1
        except Exception:
            # swallow per-row insert errors; continue
            continue

    if inserted:
        con.commit()
    con.close()
    return inserted
