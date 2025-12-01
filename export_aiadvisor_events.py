from __future__ import annotations

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "live.db"

DDL = """
CREATE TABLE IF NOT EXISTS ai_advisor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- timestamps
    ts_utc   TEXT NOT NULL,
    ts_et    TEXT NOT NULL,

    -- what we were looking at
    symbol   TEXT NOT NULL,
    context  TEXT NOT NULL,      -- e.g. 'ENTRY', 'EXIT', 'RISK_CHECK'

    -- suggestion
    side         TEXT NOT NULL,  -- 'BUY', 'SELL', 'HOLD'
    confidence   REAL,           -- 0–100 or 0–1, we’ll decide later
    price        REAL,           -- price at time of decision (if known)

    -- explanations
    reason_short TEXT,           -- 1-line summary
    reason_long  TEXT,           -- more verbose explanation

    -- optional raw JSON blob of features / model output
    raw_json     TEXT
);
"""

def main() -> None:
    print(f"Using DB: {DB_PATH}")
    if not DB_PATH.exists():
        print(f"[FATAL] live.db not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.executescript(DDL)
        conn.commit()
        print("[OK] ai_advisor_events table ensured.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
