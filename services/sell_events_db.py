# services/sell_events_db.py
# DB-backed sell lifecycle logging for Sell Analytics (LIVE_DB is source of truth)

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Any, Dict

LIVE_DB_FILENAME = "live.db"


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    if db_path:
        return str(db_path)
    here = Path(__file__).resolve()
    return str(here.parent.parent / LIVE_DB_FILENAME)


def _table_cols(con: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _ensure_cols(con: sqlite3.Connection, table: str, wanted: dict[str, str]) -> None:
    cols = set(_table_cols(con, table))
    for name, decl in wanted.items():
        if name in cols:
            continue
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        except Exception:
            # additive best-effort only
            pass


def _get_regime_snapshot() -> dict:
    """
    Best-effort regime snapshot. Never raises.
    Expected output: {label, confidence, reason, detail, ok}
    """
    try:
        from services import market_regime as mr  # type: ignore
        for fn in ("get_market_regime_cached", "get_market_regime", "compute_market_regime"):
            if hasattr(mr, fn):
                out = getattr(mr, fn)()
                if isinstance(out, dict):
                    lab = (out.get("label") or out.get("regime") or out.get("state") or "UNKNOWN")
                    out["label"] = str(lab).upper()
                    # normalize confidence to int 0-100 if possible
                    c = out.get("confidence")
                    try:
                        if c is not None:
                            out["confidence"] = int(round(float(c)))
                    except Exception:
                        pass
                    return out
        if hasattr(mr, "LATEST") and isinstance(mr.LATEST, dict):
            out = dict(mr.LATEST)
            lab = (out.get("label") or out.get("regime") or "UNKNOWN")
            out["label"] = str(lab).upper()
            return out
    except Exception:
        pass
    return {"label": "UNKNOWN", "confidence": None, "reason": None, "detail": {}, "ok": False}


def ensure_sell_events_table(db_path: Optional[str] = None) -> None:
    p = _resolve_db_path(db_path)
    con = sqlite3.connect(p, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sell_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                event TEXT NOT NULL,
                reason TEXT,
                detail TEXT,
                order_id TEXT,
                price REAL,
                qty REAL,
                mode TEXT
            )
            """
        )
        # Additive columns for regime-aware analytics
        _ensure_cols(
            con,
            "sell_events",
            {
                "regime": "TEXT",
                "regime_conf": "INTEGER",
                "regime_reason": "TEXT",
                "overlay_json": "TEXT",
            },
        )
        # helpful indexes (best-effort)
        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_sell_events_ts ON sell_events(ts_utc)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sell_events_sym ON sell_events(symbol)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sell_events_evt ON sell_events(event)")
        except Exception:
            pass

        con.commit()
    finally:
        con.close()


def log_sell_event(
    symbol: str,
    event: str,
    reason: Optional[str] = None,
    detail: Optional[str] = None,
    order_id: Optional[str] = None,
    price: Optional[float] = None,
    qty: Optional[float] = None,
    mode: Optional[str] = None,
    ts_utc: Optional[int] = None,
    *,
    db_path: Optional[str] = None,
    overlay: Optional[dict] = None,
    regime_snapshot: Optional[dict] = None,
) -> None:
    """
    Best-effort insert into live.db sell_events.
    MUST NEVER break Sell Guard.
    """
    p = _resolve_db_path(db_path)
    con = sqlite3.connect(p, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        ensure_sell_events_table(p)

        cols = _table_cols(con, "sell_events")
        if ts_utc is None:
            ts_utc = int(time.time())

        snap = regime_snapshot or _get_regime_snapshot()
        reg = (snap.get("label") or "UNKNOWN")
        conf = snap.get("confidence")
        reas = snap.get("reason")

        row: Dict[str, Any] = {}

        # base schema
        if "ts_utc" in cols: row["ts_utc"] = int(ts_utc)
        if "symbol" in cols: row["symbol"] = str(symbol).upper()
        if "event" in cols: row["event"] = str(event).upper()
        if "reason" in cols: row["reason"] = reason
        if "detail" in cols: row["detail"] = detail
        if "order_id" in cols: row["order_id"] = order_id
        if "price" in cols: row["price"] = (None if price is None else float(price))
        if "qty" in cols: row["qty"] = (None if qty is None else float(qty))
        if "mode" in cols: row["mode"] = (mode or "LIVE")

        # new regime columns
        if "regime" in cols: row["regime"] = (None if reg is None else str(reg).upper())
        if "regime_conf" in cols:
            try:
                row["regime_conf"] = (None if conf is None else int(round(float(conf))))
            except Exception:
                row["regime_conf"] = None
        if "regime_reason" in cols: row["regime_reason"] = reas

        if "overlay_json" in cols:
            try:
                row["overlay_json"] = json.dumps(overlay, separators=(",", ":")) if overlay is not None else None
            except Exception:
                row["overlay_json"] = None

        # Insert only the columns we actually have
        keys = list(row.keys())
        if not keys:
            return

        q = f"INSERT INTO sell_events ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})"
        con.execute(q, [row[k] for k in keys])
        con.commit()
    except Exception:
        # never break sell engine
        try:
            con.close()
        except Exception:
            pass
        return
    finally:
        try:
            con.close()
        except Exception:
            pass
