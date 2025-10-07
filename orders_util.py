# orders_util.py
import time


def j(x):
    try:
        import json as _json

        return _json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(x)


def _fresh_preview(
    et, acct_key: str, sym: str, qty: int, price_type: str, limit_or_none
):
    return et.preview_equity_order(
        acct_key,
        sym,
        qty,
        (limit_or_none if price_type == "LIMIT" else None),
        action="SELL",
        price_type=price_type,
        order_term="GOOD_FOR_DAY",
        market_session="REGULAR",
    )


def _extract_core(prev: dict, qty_override: int | None):
    pr = (prev or {}).get("PreviewOrderResponse") or {}
    orders = pr.get("Order") or []
    if not orders:
        raise RuntimeError("preview missing Order[]")
    o0 = orders[0]
    instrs = o0.get("Instrument") or []
    if not instrs:
        raise RuntimeError("preview missing Instrument[]")
    i0 = instrs[0]
    prod = i0.get("Product") or {}
    symbol = str(prod.get("symbol") or "").strip()
    qty = int(qty_override if qty_override is not None else i0.get("quantity") or 0)

    # previewId as int (works in your env)
    pid = pr.get("previewId")
    if not pid:
        pids = pr.get("PreviewIds") or pr.get("previewIds") or []
        if isinstance(pids, list) and pids and isinstance(pids[0], dict):
            pid = pids[0].get("previewId") or pids[0].get("id")
    if not pid:
        raise RuntimeError("previewId not found in preview")
    pid_int = int(pid)
    return symbol, qty, pid_int


def _mk_order_market_orderlvl(sym: str, qty: int, pid_int: int):
    return {
        "PlaceOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": f"{sym.upper()}m{int(time.time()*1000)}",
            "PreviewIds": [{"previewId": pid_int}],
            "Order": [
                {
                    "Instrument": [
                        {
                            "Product": {"securityType": "EQ", "symbol": sym},
                            "orderAction": "SELL",
                            "quantityType": "QUANTITY",
                            "quantity": int(qty),
                        }
                    ],
                    "marketSession": "REGULAR",
                    "orderTerm": "GOOD_FOR_DAY",
                    "priceType": "MARKET",
                }
            ],
        }
    }


def _mk_order_market_toplvl(sym: str, qty: int, pid_int: int):
    return {
        "PlaceOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": f"{sym.upper()}m{int(time.time()*1000)}",
            "PreviewIds": [{"previewId": pid_int}],
            "marketSession": "REGULAR",
            "Order": [
                {
                    "Instrument": [
                        {
                            "Product": {"securityType": "EQ", "symbol": sym},
                            "orderAction": "SELL",
                            "quantityType": "QUANTITY",
                            "quantity": int(qty),
                        }
                    ],
                    "orderTerm": "GOOD_FOR_DAY",
                    "priceType": "MARKET",
                }
            ],
        }
    }


def place_equity_sell(
    et,
    acct_key: str,
    sym: str,
    qty: int,
    price_type="MARKET",
    limit_px: float | None = None,
    debug=False,
) -> tuple[bool, int | None]:
    """
    Returns (ok, order_id). On success, **do not** keep placing — exit your caller.
    """
    key_path = f"/accounts/{acct_key}/orders/place.json"
    max_outer = 4

    for outer in range(1, max_outer + 1):
        if debug:
            print(f"[GUARD] attempt {outer}: get preview {price_type}")
        prev = _fresh_preview(et, acct_key, sym, qty, price_type, limit_px)
        if debug:
            print(j(prev))
        try:
            symbol, q_final, pid_int = _extract_core(prev, qty)
        except Exception as e:
            if debug:
                print("[GUARD] preview parse failed:", e)
            # 9999/validator issues – bail; venue 500 – retry with fresh preview next loop
            time.sleep(0.8 * outer)
            continue

        # Try the variant you proved works first: market + order-level marketSession
        variants = [
            ("market-orderlvl", _mk_order_market_orderlvl(symbol, q_final, pid_int)),
            ("market-toplvl", _mk_order_market_toplvl(symbol, q_final, pid_int)),
        ]

        for vname, body in variants:
            try:
                if debug:
                    print(f"[GUARD] placing {vname} -> {key_path}")
                    print(j(body))
                resp = et._epost(key_path, body)
                if debug:
                    print("[GUARD] PLACE RESP")
                    print(j(resp))
                pr = (resp or {}).get("PlaceOrderResponse") or {}
                # success indicator and orderId
                msgs = (((pr.get("Order") or [{}])[0]).get("messages") or {}).get(
                    "Message"
                ) or []
                ok_msg = any(
                    ("successfully entered" in (m.get("description", "").lower()))
                    for m in msgs
                    if isinstance(m, dict)
                )
                order_ids = pr.get("OrderIds") or []
                order_id = (
                    order_ids[0].get("orderId")
                    if order_ids and isinstance(order_ids[0], dict)
                    else None
                )
                if ok_msg or order_id is not None:
                    return True, order_id
            except Exception as e:
                if debug:
                    print(f"[GUARD] {vname} failed:", e)
                # 500/code 100 => venue/transient; 9999 => validator; proceed to next variant/outer
                time.sleep(0.4)

        time.sleep(1.0 * outer)

    return False, None
