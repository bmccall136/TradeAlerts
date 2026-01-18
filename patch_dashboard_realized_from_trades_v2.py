import re
from pathlib import Path

DASH = Path(r"C:\TradeAlerts\dashboard.py")

if not DASH.exists():
    raise SystemExit(f"dashboard.py not found: {DASH}")

src = DASH.read_text(encoding="utf-8", errors="ignore")

# Idempotence
if "REALIZED_FROM_TRADES_FIX" in src:
    raise SystemExit("OK: dashboard.py already has REALIZED_FROM_TRADES_FIX")

# Start marker: the realized banner inside live_data()
start_patterns = [
    r"(?m)^\s*#\s*-{6,}\s*7\)\s*REALIZED\s*P&L.*$",
    r"(?m)^\s*#\s*-{6,}\s*7\)\s*REALIZED.*$",
    r"(?m)^\s*#\s*-{6,}.*REALIZED\s*P&L.*$",
]
start_m = None
for pat in start_patterns:
    start_m = re.search(pat, src)
    if start_m:
        break

if not start_m:
    # fallback: look for the try block that builds realized_obj_full in /live/data
    start_m = re.search(r"(?m)^\s*#\s*-{6,}.*REALIZED.*$", src)

if not start_m:
    raise SystemExit("PATCH FAIL: could not find the REALIZED P&L section header in dashboard.py")

start_idx = start_m.start()

# End marker: next section banner (# ---------- N) that is NOT 7)
end_m = None
for m in re.finditer(r"(?m)^\s*#\s*-{6,}\s*(\d+)\)\s+.*$", src[start_m.end():]):
    n = int(m.group(1))
    if n != 7:
        end_m = m
        break

if end_m:
    end_idx = start_m.end() + end_m.start()
else:
    # Fallback: end right before the "DATA: FINAL" log or before payload finalization
    m_final = re.search(r"(?m)^\s*LOG\.info\(\s*\"DATA:\s*FINAL", src[start_m.end():])
    if m_final:
        end_idx = start_m.end() + m_final.start()
    else:
        # Last-resort: end at the next blank line followed by a banner-ish comment
        raise SystemExit("PATCH FAIL: could not find the end of REALIZED section (no next banner / DATA: FINAL)")

old_block = src[start_idx:end_idx]

# Build replacement block.
# We compute realized buckets directly from the in-memory `trades` list that live_data()
# already built (falls back to existing DB buckets if trades missing).
replacement = r'''# ---------- 7) REALIZED P&L ----------
# REALIZED_FROM_TRADES_FIX:
# Prefer computing realized buckets from the *trades* list (SELL pnl), so the dashboard
# matches what $$Machine actually executed (no manual E*TRADE CSV imports).
# Falls back to live.db realized_trades buckets if trades are missing.
try:
    realized_obj_full = {}

    # denom for pct (NAV if available)
    _denom_value = float((account or {}).get("nav") or (value_obj or {}).get("net_account_value") or 0.0)

    # --- 1) Primary: compute buckets from trades list ---
    try:
        realized_obj_full = compute_realized_buckets_from_trades(
            trades or [],
            denom_value=_denom_value,
            tz_name=(settings or {}).get("realized_tz") or "America/New_York",
        )
    except Exception as _exc:
        LOG.warning("realized-from-trades compute failed: %s", _exc)
        realized_obj_full = {}

    # --- 2) Fallback: existing live.db realized_trades ---
    if not realized_obj_full:
        realized_obj_full = realized_buckets_from_live_db(str(LIVE_DB), denom_value=_denom_value)

    # Ensure keys exist
    for _k in ("day", "week", "month", "all"):
        realized_obj_full.setdefault(_k, {"pnl": 0.0, "pct": 0.0})

    realized_obj = {
        "day": realized_obj_full.get("day", {"pnl": 0.0, "pct": 0.0}),
        "week": realized_obj_full.get("week", {"pnl": 0.0, "pct": 0.0}),
        "month": realized_obj_full.get("month", {"pnl": 0.0, "pct": 0.0}),
        "all": realized_obj_full.get("all", {"pnl": 0.0, "pct": 0.0}),
    }
except Exception as _exc:
    LOG.warning("realized buckets failed: %s", _exc)
    realized_obj = {"day": {"pnl": 0.0, "pct": 0.0}, "week": {"pnl": 0.0, "pct": 0.0}, "month": {"pnl": 0.0, "pct": 0.0}, "all": {"pnl": 0.0, "pct": 0.0}}
'''

# We also need to ensure helper function exists somewhere above live_data.
# If it's missing, append it near the bottom of helpers area (before routes is fine).
helper_tag = "def compute_realized_buckets_from_trades"
if helper_tag not in src:
    helper = r'''

def compute_realized_buckets_from_trades(trades, denom_value: float = 0.0, tz_name: str = "America/New_York"):
    """Compute realized P&L buckets from executed trade records.

    Expects each trade dict to include at least:
      - action (SELL)
      - pnl (numeric) for SELL rows
      - time or trade_time (timestamp string)

    Buckets are true:
      - day: today
      - week: week-to-date (Mon -> today)
      - month: month-to-date (1st -> today)
      - all: all time (in table)

    Returns shape: {day:{pnl,pct}, week:{pnl,pct}, month:{pnl,pct}, all:{pnl,pct}}
    """
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = None

    def _to_dt(v):
        if not v:
            return None
        if isinstance(v, _dt.datetime):
            return v
        s = str(v).strip()
        # Accept ISO-ish and common formats used in this project
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
        ):
            try:
                return _dt.datetime.strptime(s, fmt)
            except Exception:
                pass
        # Last resort: try fromisoformat
        try:
            return _dt.datetime.fromisoformat(s.replace("Z", ""))
        except Exception:
            return None

    now = _dt.datetime.now(tz) if tz else _dt.datetime.now()
    today = now.date()
    week_start = today - _dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    sums = {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0}

    for t in (trades or []):
        try:
            act = (t.get("action") or t.get("side") or "").upper()
            if act != "SELL":
                continue
            pl = t.get("pnl")
            if pl is None:
                continue
            pl = float(pl)

            ts = t.get("time") or t.get("trade_time") or t.get("timestamp") or ""
            dt = _to_dt(ts)
            if dt and tz and dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            d = (dt.date() if dt else None)

            sums["all"] += pl
            if d == today:
                sums["day"] += pl
            if d and week_start <= d <= today:
                sums["week"] += pl
            if d and month_start <= d <= today:
                sums["month"] += pl
        except Exception:
            continue

    def _pct(p):
        if denom_value and denom_value != 0:
            return (p / float(denom_value)) * 100.0
        return 0.0

    return {
        "day": {"pnl": float(sums["day"]), "pct": float(_pct(sums["day"]))},
        "week": {"pnl": float(sums["week"]), "pct": float(_pct(sums["week"]))},
        "month": {"pnl": float(sums["month"]), "pct": float(_pct(sums["month"]))},
        "all": {"pnl": float(sums["all"]), "pct": float(_pct(sums["all"]))},
    }
'''

    # Insert helper near other helpers: right before first route decorator in file.
    m_route = re.search(r"(?m)^@app\.route\(", src)
    if not m_route:
        # If can't find routes, just append at end
        insert_at = len(src)
    else:
        insert_at = m_route.start()

    src = src[:insert_at] + helper + "\n" + src[insert_at:]

# Replace the realized section
src = src[:start_idx] + replacement + src[end_idx:]

DASH.write_text(src, encoding="utf-8")
print("OK: patched dashboard.py (REALIZED_FROM_TRADES_FIX)")
