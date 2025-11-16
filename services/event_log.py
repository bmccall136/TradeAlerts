import sqlite3
import os
import json
import time
import threading

# Path to the live event log DB
LOG_DB_PATH = os.environ.get(
    "LIVE_LOG_DB",
    r"C:\TradeAlerts\live_log.db",
)

_lock = threading.Lock()


def _get_conn():
    """Return a SQLite connection and ensure schema exists."""
    db_dir = os.path.dirname(LOG_DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(LOG_DB_PATH, timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            time_ms   INTEGER NOT NULL,
            type      TEXT NOT NULL,
            message   TEXT NOT NULL,
            data_json TEXT
        )
        """
    )
    return conn


def log_event(event_type: str, message: str, data: dict | None = None) -> None:
    """
    Fire-and-forget logging.

    Examples:
        log_event("NAV", "nav snapshot", {"nav": nav, "bp": bp, "pv": pv})
        log_event("SELL_GUARD", "armed scalp stop", settings)
        log_event("ERROR", "preview failed", {"status": 500, "body": body})
    """
    ts_ms = int(time.time() * 1000)

    data_json = None
    if data is not None:
        try:
            data_json = json.dumps(data, separators=(",", ":"), default=str)
        except Exception:
            data_json = None  # logging must never explode

    try:
        with _lock:
            conn = _get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO event_log (time_ms, type, message, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ts_ms, str(event_type), str(message), data_json),
                )
            conn.close()
    except Exception:
        # Silent failure – app must not break due to logging
        return
