import argparse
import datetime as dt
import json
import os

from env_alias_shim import ensure_env_aliases

ensure_env_aliases()

try:
    from services import etrade_service as et
except Exception:
    import etrade_service as et


def _now():
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser(
        description="List open (working) orders; default filters to MRNA."
    )
    ap.add_argument(
        "--symbol",
        default="MRNA",
        help="Filter by symbol (default: MRNA). Use ALL to show everything.",
    )
    args = ap.parse_args()

    aid = et.account_id_key()
    os.environ.setdefault("ETRADE_ACCOUNT_ID_KEY", aid)

    # Try common order list functions
    list_funcs = [
        getattr(et, n)
        for n in [
            "list_orders",
            "get_orders",
            "list_open_orders",
            "get_order_list",
            "orders",
        ]
        if hasattr(et, n)
    ]

    if not list_funcs:
        print("No order-listing function found on etrade_service.")
        print("Available:", [n for n in dir(et) if "order" in n.lower()])
        return

    orders = None
    err = None
    for fn in list_funcs:
        try:
            params = fn.__code__.co_varnames
            kwargs = {}
            if "account_id_key" in params:
                kwargs["account_id_key"] = aid
            # Some APIs want a time range; we’ll skip unless required
            orders = fn(**kwargs) if kwargs else fn()
            break
        except Exception as e:
            err = e
            continue

    if orders is None:
        print("Failed to pull orders.", repr(err))
        return

    # Normalize shapes
    def iter_orders(payload):
        if isinstance(payload, dict):
            for k in (
                "OrdersResponse",
                "OrderListResponse",
                "orderList",
                "Orders",
                "orders",
            ):
                if k in payload:
                    payload = payload[k]
                    break
        if isinstance(payload, dict) and "Order" in payload:
            payload = payload["Order"]
        if isinstance(payload, list):
            for row in payload:
                yield row

    # Extract key fields
    def info(row):
        oid = (
            row.get("orderId")
            or row.get("order_id")
            or row.get("OrderId")
            or row.get("id")
        )
        status = row.get("status") or row.get("orderStatus") or row.get("order_status")
        sym = (
            row.get("symbol")
            or (row.get("Product") or {}).get("symbol")
            or (row.get("Instrument") or {}).get("symbol")
        )
        side = row.get("side") or row.get("action") or row.get("orderAction")
        qty = (
            row.get("qty")
            or row.get("quantity")
            or row.get("orderedQuantity")
            or row.get("filledQuantity")
        )
        ptype = row.get("price_type") or row.get("priceType") or row.get("orderType")
        price = row.get("price") or row.get("limitPrice")
        stop = row.get("stop_price") or row.get("stopPrice")
        ts = (
            row.get("placedTime") or row.get("timePlaced") or row.get("transactionDate")
        )
        return {
            "orderId": oid,
            "status": status,
            "symbol": sym,
            "side": side,
            "qty": qty,
            "priceType": ptype,
            "price": price,
            "stopPrice": stop,
            "placed": ts,
        }

    rows = [info(r) for r in iter_orders(orders)]
    if args.symbol.upper() != "ALL":
        rows = [r for r in rows if (r["symbol"] or "").upper() == args.symbol.upper()]

    # Show only live orders (commonly: OPEN/WORKING/PENDING)
    live_keywords = {
        "OPEN",
        "WORKING",
        "PENDING",
        "QUEUED",
        "ACCEPTED",
        "LIVE",
        "PARTIAL",
    }
    live = [
        r
        for r in rows
        if (
            str(r["status"] or "").upper() in live_keywords
            or any(k in str(r["status"] or "").upper() for k in live_keywords)
        )
    ]

    if not live:
        print(f"No open/working orders found for {args.symbol}.")
        return

    print(f"Open/working orders for {args.symbol} at {_now()}:")
    for r in live:
        print(json.dumps(r, indent=2))
    print(
        "\nCopy any orderId you want to cancel and use cancel_open_orders.py --order <id>"
    )
    print(
        "Or run cancel_open_orders.py --symbol",
        args.symbol,
        "to cancel all open orders for that symbol.",
    )


if __name__ == "__main__":
    main()
