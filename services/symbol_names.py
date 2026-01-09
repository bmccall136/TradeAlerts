# services/symbol_names.py
from __future__ import annotations

import sqlite3
import time
from typing import Any, Dict, Iterable, Optional


# Cache TTL (seconds). 7 days is fine for company names.
TTL_SECONDS = 7 * 24 * 60 * 60


def _now() -> int:
    return int(time.time())


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _ensure_table(db_path: str) -> None:
    con = _connect(db_path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_names (
              symbol TEXT PRIMARY KEY,
              name   TEXT NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_symbol_names_updated ON symbol_names(updated_at)")
        con.commit()
    finally:
        con.close()


def _get_cached(db_path: str, symbol: str) -> Optional[str]:
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT name, updated_at FROM symbol_names WHERE symbol=? LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        name, updated_at = row[0], int(row[1] or 0)
        if updated_at and (_now() - updated_at) <= TTL_SECONDS and name:
            return str(name).strip()
        return None
    finally:
        con.close()


def _set_cached(db_path: str, symbol: str, name: str) -> None:
    name = str(name or "").strip()
    if not name:
        return
    con = _connect(db_path)
    try:
        con.execute(
            """
            INSERT INTO symbol_names(symbol, name, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
              name=excluded.name,
              updated_at=excluded.updated_at
            """,
            (symbol, name, _now()),
        )
        con.commit()
    finally:
        con.close()


def _deep_find_first(d: Any, keys: Iterable[str]) -> Optional[str]:
    """
    Walk arbitrary nested dict/list looking for the first matching key (case-insensitive).
    Returns the first non-empty string-ish value it finds.
    """
    want = {k.lower() for k in keys}

    def walk(x: Any) -> Optional[str]:
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(k, str) and k.lower() in want:
                    if v is None:
                        pass
                    elif isinstance(v, (str, int, float)):
                        s = str(v).strip()
                        if s:
                            return s
                r = walk(v)
                if r:
                    return r
        elif isinstance(x, list):
            for it in x:
                r = walk(it)
                if r:
                    return r
        return None

    return walk(d)


def _fetch_quote_payload(symbol: str) -> Any:
    """
    Try a few likely E*TRADE service function names. We keep this defensive because
    your etrade_service has evolved over time.
    """
    from services import etrade_service as et

    # Try common single-symbol quote helpers
    for fn_name in (
        "get_quote",
        "get_quote_detail",
        "fetch_quote",
        "fetch_etrade_quote",
        "quote",
    ):
        fn = getattr(et, fn_name, None)
        if callable(fn):
            return fn(symbol)

    # Try batch quote helpers
    for fn_name in (
        "get_quotes",
        "fetch_quotes",
        "quotes",
    ):
        fn = getattr(et, fn_name, None)
        if callable(fn):
            # Some implementations accept a list, others accept a comma string
            try:
                return fn([symbol])
            except Exception:
                return fn(symbol)

    return None


def _name_from_quote_payload(symbol: str, payload: Any) -> Optional[str]:
    """
    Extract a company/security description from a quote payload.
    We search broadly to survive shape changes.
    """
    if payload is None:
        return None

    # Common name-ish keys we see across quote payloads
    name = _deep_find_first(
        payload,
        keys=(
            "companyName",
            "CompanyName",
            "company_name",
            "securityDescription",
            "SecurityDescription",
            "symbolDescription",
            "SymbolDescription",
            "description",
            "Description",
            "longName",
            "LongName",
            "instrumentName",
            "InstrumentName",
            "name",
            "Name",
        ),
    )

    if not name:
        return None

    name = str(name).strip()

    # If the "name" is literally the symbol, it didn't help.
    if name.upper() == symbol.upper():
        return None

    return name


def get_company_name(symbol: str, db_path: str) -> Optional[str]:
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None

    _ensure_table(db_path)

    cached = _get_cached(db_path, symbol)
    if cached:
        return cached

    payload = _fetch_quote_payload(symbol)
    name = _name_from_quote_payload(symbol, payload)
    if name:
        _set_cached(db_path, symbol, name)
        return name

    return None


def enrich_holdings_names(holdings: list[dict], db_path: str) -> list[dict]:
    """
    Mutates holdings in-place (and returns it) by filling h["name"] when missing or equal to symbol.
    """
    if not holdings:
        return holdings

    _ensure_table(db_path)

    for h in holdings:
        sym = str(h.get("symbol") or "").strip().upper()
        if not sym:
            continue

        cur = str(h.get("name") or "").strip()
        if cur and cur.upper() != sym:
            continue

        name = get_company_name(sym, db_path=db_path)
        if name:
            h["name"] = name

    return holdings
