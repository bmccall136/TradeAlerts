@'
import os, sys, json
from datetime import datetime, timedelta

# Ensure we can import "services" when running from anywhere
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import only the primitives that work
from services.etrade_service import (
    get_account_summary,
    get_positions,
    list_executed_orders,
    list_trade_transactions,
)

def _ymd(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:
        return {"error": str(e)}

def build_recent_trades_and_realized(days: int = 30):
    """Rebuild what your broken helper should do, without relying on it."""
    # recent trades from orders
    orders = safe(list_executed_orders, days)
    trades = []
    try:
        raw_orders = orders.get("OrderListResponse", {}).get("orders", []) or []
        for o in raw_orders:
            ts = o.get("executedTime") or o.get("placedTime") or o.get("updateTime")
            for leg in (o.get("orderLegs") or []):
                sym  = (leg.get("symbol") or "").upper()
                side = (leg.get("side") or o.get("orderAction") or "").upper()
                for ex in (leg.get("executions") or []):
                    price = float(ex.get("avgExecPrice") or ex.get("price") or 0)
                    qty   = int(ex.get("quantity") or 0)
                    amt   = round(price * qty * (1 if side == "SELL" else -1), 2)
                    trades.append({
                        "time": ts,
                        "symbol": sym,
                        "action": side,
                        "qty": qty,
                        "price": price,
                        "amount": amt,
                    })
        trades.sort(key=lambda x: str(x.get("time","")), reverse=True)
        trades = trades[:50]
    except Exception as e:
        trades = [{"error": f"orders parse failed: {e}"}]

    # realized P&L sum from transactions
    realized = 0.0
    tx = safe(list_trade_transactions, days)
    try:
        for t in (tx.get("TransactionListResponse", {}).get("transactions", []) or []):
            gl = t.get("gainLoss") or t.get("gain")
            if gl is not None:
                realized += float(gl)
        realized = round(realized, 2)
    except Exception as e:
        realized = {"error": f"transactions parse failed: {e}"}

    return trades, realized

def main():
    out = {
        "when_utc": datetime.utcnow().isoformat(),
        "balances": safe(get_account_summary),
        "positions": safe(get_positions),
    }

    # Add a tiny probe in case positions returns non-JSON
    try:
        # If positions failed with {"error": "..."} keep that for visibility.
        if isinstance(out["positions"], dict) and "error" in out["positions"]:
            out["positions_probe"] = "get_positions raised (see positions.error)"
    except Exception:
        pass

    trades, realized = build_recent_trades_and_realized(30)
    out["recent_trades"] = trades
    out["realized_pnl_sum"] = realized

    print(json.dumps(out, indent=2, default=str))

if __name__ == "__main__":
    main()
'@ | Set-Content -Path C:\TradeAlerts\tools\dump_etrade.py -Encoding UTF8
