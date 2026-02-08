# services/trigger_fires_db.py
# BUY trigger row persistence (schema-flexible)
# live.db is authoritative; CSV remains debug/audit.

import sqlite3
from datetime import datetime, timezone

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def _cols(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def ensure_trigger_fires_table(db_path: str) -> None:
    # Do NOT enforce a specific schema here; just ensure table exists minimally.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trigger_fires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT,
            symbol TEXT
        )
        """)
        conn.commit()
    finally:
        conn.close()

def insert_trigger_fire(
    db_path: str,
    symbol: str,
    price: float | None,
    source: str | None,
    notes: str | None,
    signals_pretty: str | None,
    *,
    ts_utc: str | None = None,
    day_et: str | None = None,
    time_et: str | None = None,
    side: str | None = "BUY",
    stage: str | None = "trigger",
    mode: str | None = None,
    detail: str | None = None,
) -> None:
    ensure_trigger_fires_table(db_path)
    ts_utc = ts_utc or _utc_now_iso()

    conn = sqlite3.connect(db_path)
    try:
        cols = set(_cols(conn, "trigger_fires"))

        row = {
            "ts_utc": ts_utc,
            "symbol": symbol,
            "price": price,
            "source": source,
            "notes": notes,
            "signals_pretty": signals_pretty,
            "day_et": day_et,
            "time_et": time_et,
            "side": side,
            "stage": stage,
            "mode": mode,
            "detail": detail,
        }

        use_cols = [k for k in row.keys() if k in cols]
        vals = [row[k] for k in use_cols]

        if not use_cols:
            # Nothing to insert (shouldn't happen), fail silently by design.
            return

        qcols = ",".join(use_cols)
        qmarks = ",".join(["?"] * len(use_cols))
        conn.execute(f"INSERT INTO trigger_fires ({qcols}) VALUES ({qmarks})", vals)
        conn.commit()
    finally:
        conn.close()
# -------------------------------------------------------------------
# Backwards-compat wrapper for existing callers (e.g., triggers_logger)
# -------------------------------------------------------------------
def log_trigger_fire(*args, **kwargs) -> None:
    """
    Compatibility wrapper. Accepts either kwargs or a positional pattern.
    Ultimately forwards into insert_trigger_fire(...).
    """
    # Preferred: kwargs-only call
    if kwargs:
        try:
            return insert_trigger_fire(
                kwargs.get("db_path") or kwargs.get("db") or kwargs.get("path") or r"C:\TradeAlerts\live.db",
                kwargs.get("symbol"),
                kwargs.get("price"),
                kwargs.get("source"),
                kwargs.get("notes"),
                kwargs.get("signals_pretty"),
                ts_utc=kwargs.get("ts_utc"),
                day_et=kwargs.get("day_et"),
                time_et=kwargs.get("time_et"),
                side=kwargs.get("side") or "BUY",
                stage=kwargs.get("stage") or "trigger",
                mode=kwargs.get("mode"),
                detail=kwargs.get("detail"),
            )
        except Exception:
            return

    # Positional fallback:
    # (symbol, price, source, notes, signals_pretty, day_et?, time_et?, side?, stage?, mode?, detail?, db_path?)
    try:
        symbol = args[0] if len(args) > 0 else None
        price  = args[1] if len(args) > 1 else None
        source = args[2] if len(args) > 2 else None
        notes  = args[3] if len(args) > 3 else None
        sigs   = args[4] if len(args) > 4 else None
        day_et = args[5] if len(args) > 5 else None
        time_et= args[6] if len(args) > 6 else None
        side   = args[7] if len(args) > 7 else "BUY"
        stage  = args[8] if len(args) > 8 else "trigger"
        mode   = args[9] if len(args) > 9 else None
        detail = args[10] if len(args) > 10 else None
        db_path= args[11] if len(args) > 11 else r"C:\TradeAlerts\live.db"

        return insert_trigger_fire(
            db_path, symbol, price, source, notes, sigs,
            day_et=day_et, time_et=time_et, side=side, stage=stage, mode=mode, detail=detail
        )
    except Exception:
        return
