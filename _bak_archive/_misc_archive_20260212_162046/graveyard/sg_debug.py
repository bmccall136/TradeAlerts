# sg_debug.py — print per-symbol sell decisions with FIFO basis
import datetime as dt
import json
import os

from services import etrade_service as et


def _to_f(x):
    try:
        if x is None:
            return None
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


def _ms(x):
    try:
        if isinstance(x, (int, float)):
            v = float(x)
            return int(v if v > 1e10 else v * 1000)
        s = str(x or "").strip()
        if not s:
            return 0
        if " " in s and "T" not in s:
            s = s.replace(" ", "T")
        if "Z" not in s and "+" not in s:
            s += "Z"
        return int(
            dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000
        )
    except Exception:
        return 0


# Load thresholds from live_settings.json (best-effort defaults if keys differ)
CFG_PATH = os.path.join("C:\\TradeAlerts", "live_settings.json")
tp_pct = 2.0  # take-profit %
sl_pct = -3.0  # stop-loss %
min_hold_min = 5  # minutes
try:
    cfg = json.load(open(CFG_PATH, encoding="utf-8"))
    gr = cfg.get("guardrails") or cfg.get("sell_guard") or {}
    tp_pct = float(gr.get("take_profit_pct", tp_pct))
    sl_pct = float(gr.get("stop_loss_pct", sl_pct))
    min_hold_min = int(gr.get("min_hold_minutes", min_hold_min))
except Exception:
    pass

print(
    f"[CFG] take_profit={tp_pct:.2f}%  stop_loss={sl_pct:.2f}%  min_hold={min_hold_min}m"
)

# Positions (qty by symbol)
inv = et.long_qty_map() or {}
if not inv:
    print("No holdings. Nothing to sell.")
    raise SystemExit(0)


# Recent trades to reconstruct FIFO basis for *current* shares
def fifo_basis_for_current(trades, inv_map):
    """
    Return {SYM: {"basis": avg_cost_for_current_shares, "opened_ms": earliest_lot_time}}
    using FIFO consumption of BUY lots minus SELLs.
    """
    # Build remaining BUY lots after applying all SELLs (FIFO)
    lots = {}  # sym -> [[qty, px, time_ms], ...]   oldest first
    for t in sorted(trades, key=lambda r: _ms(r.get("time_ms"))):
        s = (t.get("symbol") or "").upper()
        a = (t.get("action") or "").upper()
        q = int(_to_f(t.get("qty")) or 0)
        px = _to_f(t.get("price"))
        tms = _ms(t.get("time_ms") or t.get("time_utc") or t.get("time"))
        if not s or q <= 0 or (px or 0) <= 0:
            continue
        lots.setdefault(s, [])
        if a == "BUY":
            lots[s].append([q, px, tms])
        elif a == "SELL":
            remain = q
            while remain > 0 and lots[s]:
                lq, lpx, lts = lots[s][0]
                take = min(remain, lq)
                lq -= take
                remain -= take
                if lq == 0:
                    lots[s].pop(0)
                else:
                    lots[s][0][0] = lq

    # Compute average basis for the *current* position size (clip FIFO lots to qty)
    out = {}
    for s, qty in inv_map.items():
        q_needed = int(_to_f(qty) or 0)
        if q_needed <= 0:
            continue
        stk = lots.get(s.upper()) or []
        if not stk:
            continue

        basis_cost = 0.0
        basis_sh = 0
        opened_ts = []

        remain = q_needed
        for lq, lpx, lts in stk:
            if remain <= 0:
                break
            take = min(remain, lq)
            if take > 0:
                basis_cost += take * (lpx or 0.0)
                basis_sh += take
                opened_ts.append(lts or 0)
                remain -= take

        avg_basis = (basis_cost / basis_sh) if basis_sh else None
        opened_ms = min([ts for ts in opened_ts if ts], default=0)
        out[s.upper()] = {"basis": avg_basis, "opened_ms": opened_ms}
    return out


# Pull trades (transactions preferred)
trades = []
try:
    if hasattr(et, "transactions_as_trades"):
        trades = et.transactions_as_trades(30) or []
except Exception:
    trades = []
if not trades:
    trades = et.recent_executions_as_trades(250) or []

basis_map = fifo_basis_for_current(trades, inv)


# Quotes
def last_for(sym):
    try:
        raw = et.get_quote(sym, detailFlag="ALL") or {}
        qd = (
            (raw.get("QuoteResponse") or {}).get("QuoteData")
            or raw.get("QuoteData")
            or []
        )
        if isinstance(qd, dict):
            qd = [qd]
        last = None
        prev = None
        if qd:
            allb = qd[0].get("All") or {}
            last = _to_f(allb.get("lastTrade") or allb.get("lastPrice"))
            prev = _to_f(allb.get("previousClose") or allb.get("priorClose"))
        return last, prev
    except Exception:
        return None, None


print("\nSYMBOL   QTY   LAST   BASIS   PNL%   HELD(min)   DECISION")
now_ms = int(dt.datetime.utcnow().timestamp() * 1000)
for s, qty in sorted(inv.items()):
    q = int(_to_f(qty) or 0)
    last, prev = last_for(s)
    basis = (basis_map.get(s, {}) or {}).get("basis")
    opened_ms = (basis_map.get(s, {}) or {}).get("opened_ms") or 0
    held_min = int((now_ms - opened_ms) / 60000) if opened_ms else 0
    pnl_pct = 0.0
    if basis and last:
        pnl_pct = (last / basis - 1.0) * 100.0
    decision = "HOLD"
    reason = "no basis/price"
    if basis and last:
        reason = f"pnl={pnl_pct:+.2f}% tp>={tp_pct} sl<={sl_pct} held={held_min}m"
        if held_min >= min_hold_min and pnl_pct >= tp_pct:
            decision = "SELL (take-profit)"
        elif held_min >= min_hold_min and pnl_pct <= sl_pct:
            decision = "SELL (stop-loss)"
    print(
        f"{s:6}  {q:3d}  {last if last else '-':>6}  {basis if basis else '-':>6}  {pnl_pct:6.2f}%  {held_min:8}   {decision}  [{reason}]"
    )
