# services/buy_events_db.py
# BUY analytics events (DB-backed) with market regime stamping at insert-time.
# Single source of truth: LIVE_DB (SQLite). UTC in DB; render ET in UI.

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, Optional, Tuple


# --- MM_BUY_EVENTS_REGIME_STAMP_V1 ---
import time as _mm_time

def _mm_sqlite_has_col(conn, table, col):
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        return col in cols
    except Exception:
        return False

def _mm_buy_events_ensure_regime_cols(conn):
    # Idempotent: add columns if missing
    try:
        cur = conn.cursor()
        if not _mm_sqlite_has_col(conn, "buy_events", "regime"):
            cur.execute("ALTER TABLE buy_events ADD COLUMN regime TEXT")
        if not _mm_sqlite_has_col(conn, "buy_events", "regime_conf"):
            cur.execute("ALTER TABLE buy_events ADD COLUMN regime_conf INTEGER")
        if not _mm_sqlite_has_col(conn, "buy_events", "regime_reason"):
            cur.execute("ALTER TABLE buy_events ADD COLUMN regime_reason TEXT")
        conn.commit()
    except Exception:
        # Never break BUY logging because schema alter failed
        try: conn.rollback()
        except Exception: pass

def _mm_regime_for_ts(conn, ts_utc):
    # Prefer nearest <= ts_utc; fallback latest; else UNKNOWN
    try:
        cur = conn.cursor()
        # nearest at/before ts_utc
        cur.execute(
            "SELECT regime, conf, reason, ts_utc "
            "FROM market_regime_samples "
            "WHERE ts_utc IS NOT NULL AND ts_utc <= ? "
            "ORDER BY ts_utc DESC LIMIT 1",
            (int(ts_utc),)
        )
        row = cur.fetchone()
        if row and row[0]:
            return (row[0], int(row[1] or 0), row[2] or "")
        # fallback: latest
        cur.execute(
            "SELECT regime, conf, reason "
            "FROM market_regime_samples "
            "WHERE ts_utc IS NOT NULL "
            "ORDER BY ts_utc DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row and row[0]:
            return (row[0], int(row[1] or 0), row[2] or "")
    except Exception:
        pass
    return ("UNKNOWN", 0, "")
# --- /MM_BUY_EVENTS_REGIME_STAMP_V1 ---
def _default_db_path() -> str:
    # Prefer LIVE_DB env if present; else project-root live.db
    p = os.environ.get("LIVE_DB")
    if p:
        return p
    here = os.path.dirname(__file__)
    return os.path.join(os.path.dirname(here), "live.db")

def ensure_buy_events_schema(db_path: str) -> None:
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS buy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                event TEXT NOT NULL,
                mode TEXT,
                price REAL,
                qty REAL,
                note TEXT,
                regime TEXT,
                regime_conf INTEGER,
                regime_reason TEXT,
                overlay_json TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_buy_events_ts ON buy_events(ts_utc)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_buy_events_sym ON buy_events(symbol)")
        con.commit()

def _get_live_mode_str() -> str:
    # live_mode.txt is authoritative in this project; fall back to LIVE
    try:
        here = os.path.dirname(__file__)
        p = os.path.join(os.path.dirname(here), "live_mode.txt")
        if os.path.exists(p):
            s = open(p, "r", encoding="utf-8", errors="ignore").read().strip()
            if s:
                return s.upper()
    except Exception:
        pass
    return "LIVE"

def _safe_market_regime_snapshot() -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Robustly query services.market_regime for current regime.
    We try a few likely function names to avoid brittle coupling.
    Returns (regime, conf_int, reason).
    """
    try:
        from services import market_regime as mr  # type: ignore
    except Exception:
        return (None, None, None)

    # Candidates (return may be dict or tuple)
    fn_names = [
        "get_market_regime_snapshot",
        "market_regime_snapshot",
        "get_market_regime",
        "current_market_regime",
        "compute_market_regime",
        "get_regime",
    ]

    for name in fn_names:
        fn = getattr(mr, name, None)
        if callable(fn):
            try:
                out = fn()
                # dict form
                if isinstance(out, dict):
                    r = (

                        out.get("regime")

                        or out.get("scheme")

                        or out.get("state")

                        or out.get("label")

                        or out.get("market_regime")

                        or out.get("name")

                        or out.get("mode")

                    )

                    c = (

                        out.get("conf")

                        or out.get("confidence")

                        or out.get("regime_conf")

                        or out.get("confidence_pct")

                        or out.get("conf_pct")

                    )

                    reason = (

                        out.get("reason")

                        or out.get("regime_reason")

                        or out.get("why")

                        or out.get("details")

                    )
                    try:
                        c_int = int(round(float(c))) if c is not None else None
                    except Exception:
                        c_int = None
                    return (str(r).upper() if r else None, c_int, str(reason) if reason else None)
                # tuple/list form
                if isinstance(out, (tuple, list)) and len(out) >= 1:
                    r = out[0]
                    c = out[1] if len(out) > 1 else None
                    reason = out[2] if len(out) > 2 else None
                    try:
                        c_int = int(round(float(c))) if c is not None else None
                    except Exception:
                        c_int = None
                    return (str(r).upper() if r else None, c_int, str(reason) if reason else None)
            except Exception:
                continue

    return (None, None, None)

def log_buy_event(
    symbol: str,
    event: str,
    *,
    db_path: Optional[str] = None,
    mode: Optional[str] = None,
    price: Optional[float] = None,
    qty: Optional[float] = None,
    note: Optional[str] = None,
    overlay: Optional[Dict[str, Any]] = None,
    ts_utc: Optional[int] = None,
) -> None:
    """
    Insert one buy_event row. Always safe: exceptions are swallowed by callers.
    Regime is stamped at insert-time from services.market_regime.
    """
    if not symbol or not event:
        return

    dbp = db_path or _default_db_path()
    ensure_buy_events_schema(dbp)

    ts = int(ts_utc if ts_utc is not None else time.time())
    sym = str(symbol).upper().strip()
    ev  = str(event).upper().strip()
    md  = (mode or _get_live_mode_str()).upper().strip()

    regime, conf, reason = _safe_market_regime_snapshot()

    overlay_json = None
    if overlay is not None:
        try:
            overlay_json = json.dumps(overlay, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            overlay_json = None

    with sqlite3.connect(dbp) as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO buy_events (
                ts_utc, symbol, event, mode, price, qty, note,
                regime, regime_conf, regime_reason, overlay_json
            ) 
        # --- MM_BUY_EVENTS_REGIME_STAMP_APPLY_V1 ---
        try:
            _mm_buy_events_ensure_regime_cols(conn)
                # Prefer the inserted row's own ts_utc for regime lookup
    _mm_ts_utc = None
    try:
        if _mm_rowid:
            _mm_cur2 = conn.cursor()
            _mm_cur2.execute('SELECT ts_utc FROM buy_events WHERE rowid=?', (int(_mm_rowid),))
            _mm_r = _mm_cur2.fetchone()
            if _mm_r and _mm_r[0] is not None:
                _mm_ts_utc = int(_mm_r[0])
    except Exception:
        _mm_ts_utc = None
    if _mm_ts_utc is None:
        _mm_ts_utc = int(_mm_time.time())
            _mm_reg, _mm_conf, _mm_reason = _mm_regime_for_ts(conn, _mm_ts_utc)
            _mm_rowid = getattr(cur, "lastrowid", None)
            if _mm_rowid:
                cur.execute(
                    "UPDATE buy_events SET regime=?, regime_conf=?, regime_reason=? WHERE rowid=?",
                    (_mm_reg, int(_mm_conf or 0), _mm_reason or "", int(_mm_rowid))
                )
                try: conn.commit()
                except Exception: pass
        except Exception:
            # never break BUY logging
            try: conn.rollback()
            except Exception: pass
        # --- /MM_BUY_EVENTS_REGIME_STAMP_APPLY_V1 ---
VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ts, sym, ev, md,
            float(price) if price is not None else None,
            float(qty) if qty is not None else None,
            str(note) if note is not None else None,
            regime, conf, reason, overlay_json
        ))
        con.commit()
