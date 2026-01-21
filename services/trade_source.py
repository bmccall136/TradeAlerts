# services/trade_source.py
from __future__ import annotations

import datetime as _dt
import re
from collections import deque
from typing import Any

try:
    from zoneinfo import ZoneInfo

    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = _dt.timezone(_dt.timedelta(hours=-5))

from . import etrade_service as et

# ───────────────────────── Time helpers ─────────────────────────


def _now_et() -> _dt.datetime:
    return _dt.datetime.now(tz=_ET)


def _as_et(dt: _dt.datetime) -> _dt.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_ET)
    return dt.astimezone(_ET)


def _parse_any_dt(s: Any) -> _dt.datetime | None:
    if s is None:
        return None
    try:
        f = float(s)
        if f > 10_000_000_000:
            f /= 1000.0
        return _as_et(_dt.datetime.fromtimestamp(f, tz=_dt.UTC))
    except Exception:
        pass
    if isinstance(s, str):
        ss = s.strip()
        if not ss:
            return None
        iso = ss[:-1] + "+00:00" if ss.endswith("Z") else ss
        try:
            return _as_et(_dt.datetime.fromisoformat(iso))
        except Exception:
            pass
        # "12:03:23 EDT 09-19-2025"
        try:
            parts = ss.split()
            if len(parts) == 4 and parts[1] in ("EST", "EDT"):
                t, mdY = parts[0], parts[2]
                dt = _dt.datetime.strptime(f"{t} {mdY}", "%H:%M:%S %m-%d-%Y")
                return _as_et(dt)
        except Exception:
            pass
        try:
            tmp = ss[:-3] if ss.endswith(" ET") else ss
            if "." in tmp:
                base, frac = tmp.split(".", 1)
                i = 0
                while i < len(frac) and frac[i].isdigit():
                    i += 1
                tmp2 = base + (frac[i:] if i < len(frac) else "")
                return _as_et(_dt.datetime.fromisoformat(tmp2))
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return _as_et(_dt.datetime.strptime(ss, fmt))
            except Exception:
                pass
    return None


def _date_range(
    days: int | None, start_iso: str | None
) -> tuple[_dt.datetime, _dt.datetime]:
    end_dt = _now_et()
    if start_iso:
        try:
            y, m, d = [int(x) for x in start_iso.split("-")]
            start_dt = _as_et(_dt.datetime(y, m, d))
        except Exception:
            start_dt = end_dt - _dt.timedelta(days=30)
    else:
        days = max(1, min(int(days or 30), 90))
        start_dt = end_dt - _dt.timedelta(days=days)
    return (start_dt, end_dt)


# ─────────────────────── Normalization / merge ───────────────────────


def _upper(val: str | None) -> str:
    return (val or "").upper()


_SELL_PAT = re.compile(r"\bSELL|SOLD|SELL\s*TO\s*CLOSE|SELL\s*SHORT\b", re.I)
_BUY_PAT = re.compile(r"\bBUY|BOUGHT|BUY\s*TO\s*OPEN|BUY\s*TO\s*COVER\b", re.I)


def _infer_side(row: dict[str, Any], qty: float) -> str:
    """
    Determine BUY/SELL using a lot of hints. Order of precedence:
    1) Explicit fields: side, orderAction, transactionType, action
    2) positionEffect (closing → SELL; opening → BUY)
    3) description / memo text matching
    4) sign of amount/netAmount/total (E*TRADE sells are typically credits: +)
    5) sign of quantity (negative → SELL)
    6) fallback BUY
    """
    # 1) explicit fields
    for key in ("side", "orderAction", "transactionType", "action", "orderType"):
        v = _upper(row.get(key))
        if v in ("BUY", "BUY_TO_OPEN", "BUY_TO_COVER", "BOUGHT"):
            return "BUY"
        if v in ("SELL", "SELL_TO_CLOSE", "SELL_SHORT", "SOLD"):
            return "SELL"

    # 2) position effect
    v = _upper(row.get("positionEffect"))
    if "CLOS" in v:  # CLOSING, CLOSE
        return "SELL"
    if "OPEN" in v:
        return "BUY"

    # 3) description-like text
    desc = " ".join(
        str(row.get(k) or "")
        for k in ("description", "memo", "activityDesc", "details")
    )
    if _SELL_PAT.search(desc):
        return "SELL"
    if _BUY_PAT.search(desc):
        return "BUY"

    # 4) amount sign (credits positive, debits negative)
    for key in ("amount", "netAmount", "total", "cash"):
        try:
            amt = float(row.get(key))
            if amt > 0:
                return "SELL"
            if amt < 0:
                return "BUY"
        except Exception:
            pass

    # 5) quantity sign
    if qty < 0:
        return "SELL"

    # 6) default
    return "BUY"


def _norm_trade(row: dict[str, Any]) -> dict[str, Any]:
    symbol = (
        row.get("symbol")
        or row.get("Symbol")
        or (row.get("Product") or {}).get("symbol")
        or row.get("symbolDescription")
        or ""
    )
    symbol = str(symbol).strip().upper()

    qty_val = (
        row.get("qty")
        or row.get("quantity")
        or row.get("Quantity")
        or row.get("orderedQuantity")
        or row.get("filledQuantity")
    )
    try:
        qty = float(qty_val or 0)
    except Exception:
        qty = 0.0

    price_val = (
        row.get("price")
        or row.get("Price")
        or row.get("executionPrice")
        or row.get("executedPrice")
        or row.get("avgExecutionPrice")
        or row.get("pricePaid")
    )
    try:
        price = float(price_val or 0)
    except Exception:
        price = 0.0

    t = (
        row.get("time")
        or row.get("transactionDate")
        or row.get("dateTime")
        or row.get("executedTime")
        or row.get("timeOfExecution")
        or row.get("orderTime")
        or row.get("tradeDate")
        or row.get("timeUTC")
    )
    dt = _parse_any_dt(t)
    time_iso = dt.isoformat() if dt else None
    time_ms = int(dt.timestamp() * 1000) if dt else None

    side = _infer_side(row, qty)

    src = row.get("_source") or "unknown"
    id_parts = [
        row.get("orderId")
        or row.get("orderNumber")
        or row.get("transactionId")
        or row.get("executionId")
        or "",
        symbol,
        f"{qty:g}",
        f"{price:.4f}",
        time_iso or str(time_ms or ""),
    ]
    id_key = "|".join(str(p) for p in id_parts)

    return {
        "symbol": symbol,
        "side": side,
        "action": side,
        "qty": qty,
        "price": price,
        "time": time_iso,
        "time_ms": time_ms,
        "_source": src,
        "_id": id_key,
        "price_paid": None,
        "amount": None,
        "pl": None,
        "pl_pct": None,
        "_raw": row,
    }


def _merge_dedup(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        k = r.get("_id")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(r)
    out.sort(key=lambda x: (x.get("time_ms") or 0), reverse=True)
    return out


# ─────────────── Fetch: executions & transactions ───────────────


def _fetch_executions(
    start_dt: _dt.datetime, end_dt: _dt.datetime, max_count: int = 800
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if hasattr(et, "list_executed_orders_between"):
        page = 1
        while len(out) < max_count:
            batch = et.list_executed_orders_between(start_dt, end_dt, page=page)  # type: ignore[attr-defined]
            if not batch:
                break
            for b in batch:
                b["_source"] = "executions"
                out.append(_norm_trade(b))
            if len(batch) < 50:
                break
            page += 1
        return out

    if hasattr(et, "recent_executions_as_trades"):
        try:
            batch = et.recent_executions_as_trades(min(max_count, 1000))  # type: ignore[attr-defined]
            for b in batch or []:
                b["_source"] = "executions_recent"
                nr = _norm_trade(b)
                dt = _parse_any_dt(nr.get("time"))
                if dt and start_dt <= dt < end_dt:
                    out.append(nr)
            return out
        except Exception:
            pass

    if hasattr(et, "list_executed_orders_recent"):
        try:
            batch = et.list_executed_orders_recent(min(max_count, 1000))  # type: ignore[attr-defined]
            for b in batch or []:
                b["_source"] = "executions_recent_raw"
                nr = _norm_trade(b)
                dt = _parse_any_dt(nr.get("time"))
                if dt and start_dt <= dt < end_dt:
                    out.append(nr)
            return out
        except Exception:
            pass

    return out


def _fetch_transactions(
    start_dt: _dt.datetime, end_dt: _dt.datetime, max_count: int = 800
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sd, ed = start_dt.date(), end_dt.date()

    if hasattr(et, "list_transactions_between"):
        marker = None
        while len(out) < max_count:
            try:
                batch, marker = et.list_transactions_between(sd, ed, marker=marker)  # type: ignore[attr-defined]
            except Exception:
                break
            if not batch:
                break
            for b in batch:
                ttype = _upper(b.get("transactionType"))
                if (
                    any(k in ttype for k in ("BUY", "SELL", "BOUGHT", "SOLD"))
                    or _SELL_PAT.search(str(b))
                    or _BUY_PAT.search(str(b))
                ):
                    b["_source"] = "transactions"
                    nr = _norm_trade(b)
                    dt = _parse_any_dt(nr.get("time"))
                    if dt and start_dt <= dt < end_dt:
                        out.append(nr)
            if not marker:
                break
        return out

    if hasattr(et, "list_transactions"):
        try:
            step = _dt.timedelta(days=7)
            s = sd
            while s < ed:
                e = min(s + step, ed)
                batch = et.list_transactions(s, e) or []  # type: ignore[attr-defined]
                for b in batch:
                    ttype = _upper(b.get("transactionType"))
                    if (
                        any(k in ttype for k in ("BUY", "SELL", "BOUGHT", "SOLD"))
                        or _SELL_PAT.search(str(b))
                        or _BUY_PAT.search(str(b))
                    ):
                        b["_source"] = "transactions_simple"
                        nr = _norm_trade(b)
                        dt = _parse_any_dt(nr.get("time"))
                        if dt and start_dt <= dt < end_dt:
                            out.append(nr)
                s = e
            return out
        except Exception:
            pass

    if hasattr(et, "account_transactions"):
        try:
            step = _dt.timedelta(days=7)
            s = sd
            while s < ed:
                e = min(s + step, ed)
                batch = et.account_transactions(s, e) or []  # type: ignore[attr-defined]
                for b in batch:
                    ttype = _upper(b.get("transactionType"))
                    if (
                        any(k in ttype for k in ("BUY", "SELL", "BOUGHT", "SOLD"))
                        or _SELL_PAT.search(str(b))
                        or _BUY_PAT.search(str(b))
                    ):
                        b["_source"] = "transactions_account"
                        nr = _norm_trade(b)
                        dt = _parse_any_dt(nr.get("time"))
                        if dt and start_dt <= dt < end_dt:
                            out.append(nr)
                s = e
            return out
        except Exception:
            pass

    return out


# ───────────────────── Realized P&L (FIFO) ─────────────────────


def _enrich_fifo_realized_pl(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda r: (r.get("time_ms") or 0))
    lots: dict[str, deque[tuple[float, float]]] = {}
    out: list[dict[str, Any]] = []

    for r in ordered:
        sym = r["symbol"]
        side = r["side"]
        qty = float(r["qty"] or 0)
        px = float(r["price"] or 0)

        if sym not in lots:
            lots[sym] = deque()

        if side == "BUY":
            if qty > 0:
                lots[sym].append((qty, px))
            out.append(r)
            continue

        if side == "SELL":
            sell_qty = qty if qty > 0 else -qty
            basis_amt = 0.0
            basis_qty = 0.0
            while sell_qty > 0 and lots[sym]:
                lot_qty, lot_px = lots[sym][0]
                take = min(lot_qty, sell_qty)
                basis_amt += take * lot_px
                basis_qty += take
                lot_qty -= take
                sell_qty -= take
                if lot_qty <= 1e-9:
                    lots[sym].popleft()
                else:
                    lots[sym][0] = (lot_qty, lot_px)
            if sell_qty > 0:
                # Not enough BUY lots in our local FIFO window.
                # DO NOT invent $0 basis (that turns proceeds into fake "P/L").
                rr = dict(r)
                rr["price_paid"] = None
                rr["amount"] = round(px * basis_qty, 4) if basis_qty else None
                rr["pl"] = None
                rr["pl_pct"] = None
                rr["_poison"] = True
                out.append(rr)
                continue

            if basis_qty > 0:
                avg_basis = basis_amt / basis_qty if basis_qty else 0.0
                realized = (px - avg_basis) * basis_qty
                rr = dict(r)
                rr["price_paid"] = round(avg_basis, 4) if basis_qty else None
                rr["amount"] = round(px * basis_qty, 4)
                rr["pl"] = round(realized, 4)
                rr["pl_pct"] = (
                    round(((px - avg_basis) / avg_basis) * 100.0, 4)
                    if avg_basis
                    else None
                )
                out.append(rr)
            else:
                out.append(r)
            continue

        out.append(r)

    out.sort(key=lambda x: (x.get("time_ms") or 0), reverse=True)
    return out


# ────────────────────────── Public API ──────────────────────────


def load_trades_merged(
    days: int | None = None, start_iso: str | None = None, max_count: int = 800
) -> list[dict[str, Any]]:
    start_dt, end_dt = _date_range(days, start_iso)
    execs = _fetch_executions(start_dt, end_dt, max_count=max_count)
    txns = _fetch_transactions(start_dt, end_dt, max_count=max_count)
    merged_desc = _merge_dedup(execs + txns)  # newest-first (for UI)
    merged_asc = list(reversed(merged_desc))  # oldest-first (for FIFO)
    enriched_asc = _enrich_fifo_realized_pl(merged_asc)
    enriched = list(reversed(enriched_asc))  # back to newest-first (for UI)
    final_rows: list[dict[str, Any]] = []
    for r in enriched[:max_count]:
        dt = _parse_any_dt(r.get("time"))
        final_rows.append(
            {
                "symbol": r["symbol"],
                "action": r.get("action") or r.get("side"),
                "qty": r.get("qty"),
                "price": r.get("price"),
                "price_paid": r.get("price_paid"),
                "amount": r.get("amount"),
                "pl": r.get("pl"),
                "pl_pct": r.get("pl_pct"),
                "time": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
                "time_utc": dt.isoformat() if dt else None,
                "time_ms": r.get("time_ms"),
            }
        )
    return final_rows
