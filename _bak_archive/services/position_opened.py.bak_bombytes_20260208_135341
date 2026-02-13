# services/position_opened.py
# Best-effort: store per-symbol "opened" timestamp in live.db without breaking the loop.
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set


def _iso_utc(dt: Optional[datetime]) -> str:
    if not isinstance(dt, datetime):
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _table_cols(cur: sqlite3.Cursor, table: str) -> Set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {str(r[1]) for r in cur.fetchall()}  # r[1] = name


def upsert_position_opened(
    live_db_path: str,
    symbol: str,
    opened_dt: Optional[datetime] = None,
    source: str = "unknown",
) -> None:
    sym = (symbol or "").strip().upper()
    if not sym:
        return

    opened_iso = _iso_utc(opened_dt)
    now_iso = _iso_utc(datetime.now(timezone.utc))

    p = Path(live_db_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(p))
    try:
        cur = con.cursor()

        # Ensure table exists (minimal). If it already exists with older cols, this won't change it.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS position_opened (
                symbol TEXT PRIMARY KEY,
                opened_utc TEXT
            )
            """
        )

        cols = _table_cols(cur, "position_opened")

        # Pick the best available column names in the existing DB
        opened_col = None
        for c in ("opened_utc", "opened_at", "opened", "opened_time", "opened_dt", "opened_ts", "opened_iso"):
            if c in cols:
                opened_col = c
                break
        if opened_col is None:
            # As a last resort, just bail silently.
            return

        source_col = "source" if "source" in cols else None
        updated_col = None
        for c in ("updated_utc", "updated_at", "updated", "updated_time", "updated_dt"):
            if c in cols:
                updated_col = c
                break

        # Build a compatible UPSERT
        insert_cols = ["symbol", opened_col]
        insert_vals = ["?", "?"]
        params = [sym, opened_iso]

        if source_col:
            insert_cols.append(source_col)
            insert_vals.append("?")
            params.append(str(source or ""))

        if updated_col:
            insert_cols.append(updated_col)
            insert_vals.append("?")
            params.append(now_iso)

        set_parts = [f"{opened_col}=excluded.{opened_col}"]
        if source_col:
            set_parts.append(f"{source_col}=excluded.{source_col}")
        if updated_col:
            set_parts.append(f"{updated_col}=excluded.{updated_col}")

        sql = (
            f"INSERT INTO position_opened({', '.join(insert_cols)}) "
            f"VALUES ({', '.join(insert_vals)}) "
            f"ON CONFLICT(symbol) DO UPDATE SET {', '.join(set_parts)}"
        )

        cur.execute(sql, params)
        con.commit()
    finally:
        con.close()
