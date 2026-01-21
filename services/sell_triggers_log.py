# C:\TradeAlerts\services\sell_triggers_log.py
from __future__ import annotations

import csv
import json
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


# --------------------------------------------------------------------------------------
# Sell Triggers (date-named CSV files)
#
# This matches the buy-trigger style:
#   logs/sell_triggers_YYYY-MM-DD.csv
#
# - Uses EITHER local ET or UTC for "what day is it" depending on env:
#     SELL_TRIGGERS_ROTATE_UTC=true|false   (default: false => ET)
#
# - Retention:
#     SELL_TRIGGERS_BACKUP_DAYS=14 (default)
#     Will delete old sell_triggers_YYYY-MM-DD.csv beyond retention.
#
# - Never raises: logging must not crash sell_guard.
# --------------------------------------------------------------------------------------

_LOCK = threading.Lock()
_PRUNE_EVERY_SEC = 300  # prune old files at most every 5 minutes
_last_prune_ts: float = 0.0

DATE_FILE_RE = re.compile(r"^sell_triggers_(\d{4}-\d{2}-\d{2})\.csv$")

DEFAULT_COLUMNS = [
    "ts_utc",
    "ts_et",
    "symbol",
    "qty",
    "action",        # e.g. SELL, STOPLOSS, TIMEOUT, TRAIL_EXIT, TARGET_EXIT, AI_EXIT
    "reason",        # short human reason (optional)
    "pl_pct",
    "hold_min",
    "entry_price",
    "last_price",
    "order_type",    # MARKET/LIMIT/etc (optional)
    "limit_price",   # optional
    "source",        # "sell_guard" default
    "extra_json",    # any additional fields dumped as json
]


def _env_bool(name: str, default: bool = False) -> bool:
    v = str(os.environ.get(name, "")).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


def _now_et() -> datetime:
    if ZoneInfo is None:
        return datetime.now(tz=UTC)
    try:
        return datetime.now(tz=ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(tz=UTC)


def _day_key_dt() -> datetime:
    """
    The timestamp used to decide the filename date.
    Default: ET day boundary.
    If SELL_TRIGGERS_ROTATE_UTC=true, use UTC day boundary instead.
    """
    rotate_utc = _env_bool("SELL_TRIGGERS_ROTATE_UTC", default=False)
    if rotate_utc:
        return datetime.now(tz=UTC)
    return _now_et()


def _log_dir() -> Path:
    # Prefer explicit env, otherwise default to project logs/
    d = os.environ.get("SELL_TRIGGERS_DIR", "").strip()
    if d:
        p = Path(d).expanduser()
    else:
        # services/ -> project root -> logs/
        p = (Path(__file__).resolve().parent.parent / "logs").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _today_path() -> Path:
    dt = _day_key_dt()
    day = dt.strftime("%Y-%m-%d")
    return _log_dir() / f"sell_triggers_{day}.csv"


def _ensure_header(path: Path, columns: list[str]) -> None:
    try:
        if not path.exists() or path.stat().st_size == 0:
            with path.open("a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(columns)
    except Exception:
        # Never crash caller
        return


def _prune_old_files(now_ts: float) -> None:
    global _last_prune_ts
    if (now_ts - _last_prune_ts) < _PRUNE_EVERY_SEC:
        return

    backup_days = int(os.environ.get("SELL_TRIGGERS_BACKUP_DAYS", "14") or 14)
    cutoff = _day_key_dt() - timedelta(days=backup_days)

    try:
        ld = _log_dir()
        for fp in ld.iterdir():
            if not fp.is_file():
                continue
            m = DATE_FILE_RE.match(fp.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d")
                # interpret date in the same "day space" as _day_key_dt()
                # (we only need ordering, so naive is fine here)
                if d < cutoff.replace(tzinfo=None).date().__class__(d.year, d.month, d.day):
                    fp.unlink(missing_ok=True)  # py3.8+ supports missing_ok?
            except Exception:
                continue
    except Exception:
        pass
    finally:
        _last_prune_ts = now_ts


def emit_sell_event(
    *,
    symbol: str,
    qty: float,
    action: str,
    pl_pct: Optional[float] = None,
    hold_min: Optional[float] = None,
    entry_price: Optional[float] = None,
    last_price: Optional[float] = None,
    reason: str = "",
    order_type: str = "",
    limit_price: Optional[float] = None,
    source: str = "sell_guard",
    ts_utc: Optional[datetime] = None,
    **extra: Any,
) -> None:
    """
    Append a sell-trigger row to today's dated CSV file.

    This function must NEVER raise.
    """
    try:
        sym = (symbol or "").strip().upper()
        if not sym:
            return

        # timestamps
        utc_dt = ts_utc if isinstance(ts_utc, datetime) else datetime.now(tz=UTC)
        et_dt = _now_et()

        # file + header
        path = _today_path()

        # pack extra fields as JSON so schema stays stable
        extras: Dict[str, Any] = {}
        for k, v in (extra or {}).items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                extras[k] = v
            else:
                extras[k] = str(v)

        row = {
            "ts_utc": utc_dt.isoformat(),
            "ts_et": et_dt.isoformat(),
            "symbol": sym,
            "qty": float(qty or 0.0),
            "action": str(action or "").strip().upper(),
            "reason": str(reason or ""),
            "pl_pct": "" if pl_pct is None else float(pl_pct),
            "hold_min": "" if hold_min is None else float(hold_min),
            "entry_price": "" if entry_price is None else float(entry_price),
            "last_price": "" if last_price is None else float(last_price),
            "order_type": str(order_type or "").strip().upper(),
            "limit_price": "" if limit_price is None else float(limit_price),
            "source": str(source or "sell_guard"),
            "extra_json": json.dumps(extras, ensure_ascii=False) if extras else "",
        }

        with _LOCK:
            _ensure_header(path, DEFAULT_COLUMNS)
            with path.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=DEFAULT_COLUMNS, extrasaction="ignore")
                w.writerow(row)

            # retention cleanup (cheap, rate-limited)
            try:
                _prune_old_files(time.time())
            except Exception:
                pass

    except Exception:
        # Never crash caller
        return
