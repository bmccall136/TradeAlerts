# services/live_guardrails.py
import os, sqlite3, threading, time, logging
from datetime import datetime, timezone, timedelta
import pytz

from services.broker_live import market_sell
from services import etrade_service as et

log = logging.getLogger("live_guardrails")

DB_PATH = os.path.join(os.getcwd(), "simulation.db")  # reuse your existing DB
EASTERN = pytz.timezone("America/New_York")
ENABLED = (os.getenv("GUARDRAILS_ENABLED", "true").lower() in {"1","true","on","yes"})

# ── helpers for time ─────────────────────────────────────────
def now_eastern():
    return datetime.now(timezone.utc).astimezone(EASTERN)

def local_date(dt):
    if dt.tzinfo is None:  # assume UTC
        dt = dt.replace(tzinfo=timezone.utc).astimezone(EASTERN)
    else:
        dt = dt.astimezone(EASTERN)
    return dt.date()

def next_market_open_seconds():
    """
    Very simple timing: assume 09:30 ET next trading session.
    Weekends roll to Monday. (Holiday logic can be added later.)
    """
    n = now_eastern()
    target_time = n.replace(hour=9, minute=30, second=0, microsecond=0)
    if n.time() >= target_time.time():
        target_time = target_time + timedelta(days=1)
    # weekend roll
    while target_time.weekday() >= 5:  # 5=Sat,6=Sun
        target_time += timedelta(days=1)
    return max(1, int((target_time - n).total_seconds()))

# ── storage ──────────────────────────────────────────────────
def _conn():
    return sqlite3.connect(DB_PATH)

def init_table():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS live_guardrails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          symbol TEXT NOT NULL,
          qty INTEGER NOT NULL,
          opened_at TEXT NOT NULL,   -- ISO UTC
          status TEXT NOT NULL DEFAULT 'OPEN'  -- OPEN | SOLD | CANCELED
        );
        """)

def record_entry(symbol: str, qty: int):
    dt = datetime.utcnow().replace(microsecond=0).isoformat()
    with _conn() as c:
        c.execute("INSERT INTO live_guardrails(symbol, qty, opened_at, status) VALUES (?, ?, ?, 'OPEN')",
                  (symbol.upper(), int(qty), dt))
    log.info("[GR] recorded entry %s x%d at %s", symbol, qty, dt)

def list_open_entries():
    with _conn() as c:
        rows = c.execute("SELECT id, symbol, qty, opened_at, status FROM live_guardrails WHERE status='OPEN'").fetchall()
    return [{"id": r[0], "symbol": r[1], "qty": r[2], "opened_at": r[3], "status": r[4]} for r in rows]

def mark_sold(entry_id: int):
    with _conn() as c:
        c.execute("UPDATE live_guardrails SET status='SOLD' WHERE id=?", (entry_id,))

def has_bought_today():
    today = local_date(now_eastern())
    with _conn() as c:
        rows = c.execute("SELECT opened_at FROM live_guardrails WHERE status IN ('OPEN','SOLD')").fetchall()
    for (ts,) in rows:
        try:
            dt = datetime.fromisoformat(ts)  # stored UTC naive
            if local_date(dt) == today:
                return True
        except Exception:
            pass
    return False

def open_position_exists():
    return len(list_open_entries()) > 0

def should_sell_today(opened_at_iso: str) -> bool:
    try:
        dt = datetime.fromisoformat(opened_at_iso)  # UTC
    except Exception:
        return False
    return local_date(dt) < local_date(now_eastern())  # opened before today

# ── reconcile helper (optional but useful) ──────────────────
def current_qty(symbol: str) -> int:
    try:
        for p in (et.get_positions() or []):
            if (p.get("symbol") or "").upper() == symbol.upper():
                return int(p.get("qty") or 0)
    except Exception:
        pass
    return 0

# ── auto seller thread ───────────────────────────────────────
_thread = None
_started = False

def _auto_seller_loop():
    log.info("[GR] auto-seller started (enabled=%s)", ENABLED)
    while True:
        try:
            if not ENABLED:
                time.sleep(30)
                continue

            secs = next_market_open_seconds()
            time.sleep(secs)  # wake at next 09:30 ET (roughly)

            # sell everything that was opened before "today"
            for e in list_open_entries():
                if not should_sell_today(e["opened_at"]):
                    continue
                sym, qty = e["symbol"], int(e["qty"])
                # If already gone on the broker, just mark sold
                if current_qty(sym) <= 0:
                    log.info("[GR] %s already gone at broker; marking SOLD", sym)
                    mark_sold(e["id"])
                    continue

                try:
                    log.info("[GR] Selling at open: %s x%d", sym, qty)
                    market_sell(sym, qty)  # market exit
                    mark_sold(e["id"])
                    log.info("[GR] SOLD %s", sym)
                except Exception as ex:
                    log.exception("[GR] sell failed for %s: %s", sym, ex)
            # chill a bit after the burst
            time.sleep(60)
        except Exception:
            log.exception("[GR] loop error")
            time.sleep(30)

def start_guardrails_auto_seller():
    global _thread, _started
    if _started:
        return
    init_table()
    _thread = threading.Thread(target=_auto_seller_loop, daemon=True)
    _thread.start()
    _started = True
