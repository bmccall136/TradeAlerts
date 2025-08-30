import json
from datetime import datetime, timedelta

# Use the helpers you already have in services\etrade_service.py
try:
    from services.etrade_service import (
        get_account_summary,
        get_positions,
        list_executed_orders,
        list_trade_transactions,
        get_recent_trades_and_realized,
        account_id_key,  # if present
    )
except ImportError:
    from services.etrade_service import (
        get_account_summary,
        get_positions,
        list_executed_orders,
        list_trade_transactions,
        get_recent_trades_and_realized,
    )
    account_id_key = lambda: None

def safe(callable_obj, *args, **kwargs):
    try:
        return callable_obj(*args, **kwargs)
    except Exception as e:
        return {"error": str(e)}

def main():
    end = datetime.utcnow()
    out = {
        "when_utc": end.isoformat(),
        "account_id_key": safe(account_id_key),
        "balances": safe(get_account_summary),
        "positions": safe(get_positions),
        "orders_executed": safe(list_executed_orders, 30),   # last 30 days
        "transactions_trade": safe(list_trade_transactions, 30),
    }
    try:
        trades, realized = get_recent_trades_and_realized(30)
        out["recent_trades"] = trades
        out["realized_pnl_sum"] = realized
    except Exception as e:
        out["recent_trades"] = []
        out["realized_pnl_sum"] = 0.0
        out["recent_trades_error"] = str(e)

    print(json.dumps(out, indent=2, default=str))

if __name__ == "__main__":
    main()
