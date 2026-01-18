import re
from pathlib import Path

DASH = Path(r"C:\TradeAlerts\dashboard.py")
if not DASH.exists():
    raise SystemExit(f"dashboard.py not found at {DASH}")

src = DASH.read_text(encoding="utf-8", errors="ignore")

# We replace the whole section starting at the banner comment for section 7)
# and ending right before the next banner comment ("# ---------- 8)" etc).
# This keeps the edit surgical and repeatable.

start_re = re.compile(r"(?m)^\s*#\s*-{6,}\s*7\)\s*REALIZED\s*P&L.*$")
end_re = re.compile(r"(?m)^\s*#\s*-{6,}\s*8\)\s")

m_start = start_re.search(src)
if not m_start:
    raise SystemExit("PATCH FAIL: could not find the '7) REALIZED P&L' banner in dashboard.py")

m_end = end_re.search(src, m_start.end())
if not m_end:
    raise SystemExit("PATCH FAIL: could not find the '8) ...' banner after the realized section")

new_block = r'''
    # ---------- 7) REALIZED P&L (computed from trades; DB fallback) ----------
    # Goal:
    #   - Stop depending on E*TRADE Transactions (often missing gainLoss).
    #   - Prefer *computed* realized P&L from the same trade feed the UI uses.
    #   - Fall back to live.db.realized_trades if needed.
    try:
        from datetime import datetime, timezone, timedelta, date

        def _parse_trade_dt(t: dict):
            """Best-effort parse of trade time from common keys."""
            # Common keys we've seen across your codebase
            for k in ("time_et", "time", "trade_time", "timestamp", "time_utc"):
                v = t.get(k)
                if not v:
                    continue
                # epoch seconds
                if isinstance(v, (int, float)):
                    # assume seconds
                    return datetime.fromtimestamp(float(v), tz=timezone.utc)
                s = str(v).strip()
                # epoch ms
                if s.isdigit() and len(s) >= 13:
                    return datetime.fromtimestamp(int(s) / 1000.0, tz=timezone.utc)
                # ISO-ish
                s2 = s.replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(s2)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    pass
                # fallback: 'MM/DD/YYYY HH:MM:SS'
                for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
                    try:
                        dt = datetime.strptime(s, fmt)
                        return dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
            return None

        def _is_sell(t: dict) -> bool:
            a = (t.get("action") or t.get("side") or "").upper().strip()
            return a == "SELL"

        def _trade_pnl(t: dict):
            # Your merged trade feed uses 'pnl' frequently.
            for k in ("pnl", "gain", "pl", "profit"):
                v = t.get(k)
                if v is None or v == "":
                    continue
                try:
                    return float(v)
                except Exception:
                    continue
            return None

        def _bucket_sum(trades_list, start_dt_utc, end_dt_utc):
            total = 0.0
            any_hit = False
            for tr in (trades_list or []):
                if not isinstance(tr, dict):
                    continue
                if not _is_sell(tr):
                    continue
                dt = _parse_trade_dt(tr)
                if not dt:
                    continue
                # normalize to UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_utc = dt.astimezone(timezone.utc)
                if start_dt_utc <= dt_utc <= end_dt_utc:
                    pnl = _trade_pnl(tr)
                    if pnl is None:
                        continue
                    total += float(pnl)
                    any_hit = True
            return total, any_hit

        # denom for pct
        _denom_value = float((account or {}).get("nav") or (value_obj or {}).get("net_account_value") or 0.0)

        # Determine ET day/week/month boundaries using your existing ETZ if available.
        # If ETZ isn't defined for some reason, use local date boundaries.
        now_utc = datetime.now(timezone.utc)
        try:
            now_et = now_utc.astimezone(ETZ)  # type: ignore[name-defined]
        except Exception:
            now_et = now_utc

        day_start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
        # week start = Monday
        week_start_et = day_start_et - timedelta(days=day_start_et.weekday())
        month_start_et = day_start_et.replace(day=1)

        def _to_utc(dt):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        day_pl, day_hit = _bucket_sum(trades, _to_utc(day_start_et), now_utc)
        week_pl, week_hit = _bucket_sum(trades, _to_utc(week_start_et), now_utc)
        month_pl, month_hit = _bucket_sum(trades, _to_utc(month_start_et), now_utc)

        def _pct(pl: float) -> float:
            if _denom_value and _denom_value != 0.0:
                return float(pl) / float(_denom_value) * 100.0
            return 0.0

        realized_from_trades = {
            "day": {"pnl": float(day_pl), "pct": float(_pct(day_pl))},
            "week": {"pnl": float(week_pl), "pct": float(_pct(week_pl))},
            "month": {"pnl": float(month_pl), "pct": float(_pct(month_pl))},
        }

        # Fallback: DB buckets (if you still have them)
        realized_from_db = None
        try:
            realized_from_db = _realized_all_from_db(str(LIVE_DB), denom_value=_denom_value)  # type: ignore[name-defined]
        except Exception:
            realized_from_db = None

        # Decide which to publish:
        # If trades had at least one SELL with pnl in any bucket, trust it.
        use_trades = bool(day_hit or week_hit or month_hit)

        realized_obj_full = {}
        if use_trades:
            realized_obj_full.update(realized_from_trades)
            # keep existing 'all' from DB if present
            if isinstance(realized_from_db, dict):
                if "all" in realized_from_db:
                    realized_obj_full["all"] = realized_from_db.get("all")
                elif "pnl" in realized_from_db and "pct" in realized_from_db:
                    realized_obj_full["all"] = realized_from_db
        else:
            # DB-only fallback
            if isinstance(realized_from_db, dict) and ("day" in realized_from_db or "all" in realized_from_db):
                realized_obj_full = realized_from_db
            else:
                realized_obj_full.update(realized_from_trades)

        # Ensure keys exist
        for k in ("day", "week", "month"):
            realized_obj_full.setdefault(k, {"pnl": 0.0, "pct": 0.0})
        if "all" not in realized_obj_full:
            realized_obj_full["all"] = {"pnl": 0.0, "pct": 0.0}

        realized_obj = realized_obj_full

    except Exception as _exc:
        LOG.warning("realized calc failed: %s", _exc)
        try:
            realized_obj = _realized_all_from_db(str(LIVE_DB), denom_value=0.0)
        except Exception:
            realized_obj = {"day": {"pnl": 0.0, "pct": 0.0}, "week": {"pnl": 0.0, "pct": 0.0}, "month": {"pnl": 0.0, "pct": 0.0}, "all": {"pnl": 0.0, "pct": 0.0}}

    payload["realized"] = realized_obj
'''

# Splice
patched = src[:m_start.start()] + new_block + src[m_end.start():]

# Idempotence check: avoid duplicating if run twice
if "computed from trades; DB fallback" in src:
    # already patched
    raise SystemExit("dashboard.py already patched for realized-from-trades")

DASH.write_text(patched, encoding="utf-8")
print("OK: patched dashboard.py to compute Realized P&L from trades (DB fallback kept)")
