import os, sys, json, argparse

# 1) ensure env mapped (no renaming your .env)
from env_alias_shim import ensure_env_aliases
ensure_env_aliases()

# 2) import service like sell_guard does
try:
    from services import etrade_service as et
except Exception:
    import etrade_service as et

def have_mrna_qty(account_id_key: str) -> int:
    """Return integer long qty for MRNA, or 0 if none/unknown."""
    try:
        pos = et.get_positions(account_id_key)
    except TypeError:
        # some clients define zero-arg get_positions()
        pos = et.get_positions()
    sym_fields = ("symbol","Symbol")
    qty_fields = ("qty","quantity","Quantity","longQuantity","longQty","availableQty","availQty","displayableQty")
    # normalize common payload shapes
    if isinstance(pos, dict):
        for k in ("PositionsResponse","positions","PositionList","AccountPositions"):
            if k in pos:
                pos = pos[k]
                break
    rows = pos.get("Position") if isinstance(pos, dict) and "Position" in pos else pos
    if not isinstance(rows, list):
        return 0
    for row in rows:
        # get symbol
        s = None
        for f in sym_fields:
            if f in row: s = row[f]; break
        if not s and isinstance(row.get("Product"), dict):
            s = row["Product"].get("symbol")
        if (s or "").upper() != "MRNA":
            continue
        q = 0
        for f in qty_fields:
            if f in row and row[f] is not None:
                try:
                    q = int(float(row[f]))
                    break
                except Exception:
                    pass
        return max(q, 0)
    return 0

def main():
    ap = argparse.ArgumentParser(description="Preview/place a 1-share SELL for MRNA.")
    ap.add_argument("--place", action="store_true", help="Place the order (otherwise just preview).")
    args = ap.parse_args()

    aid = et.account_id_key()
    os.environ.setdefault("ETRADE_ACCOUNT_ID_KEY", aid)

    qty = have_mrna_qty(aid)
    if qty < 1:
        print("You don't appear to have a free long share of MRNA (qty found:", qty, ").")
        print("If shares are reserved by another open sell, cancel that order first.")
        sys.exit(2)

    # Build kwargs for your service's preview signature we discovered
    order_kwargs = {
        "account_id_key": aid,
        "symbol": "MRNA",
        "qty": 1,
        "action": "SELL",
        "price_type": "MARKET",
        "order_term": "GOOD_FOR_DAY",
        "market_session": "REGULAR",
        "price": None,
    }

    # 3) PREVIEW
    try:
        preview = et.preview_equity_order(**{k:v for k,v in order_kwargs.items()
                                             if k in et.preview_equity_order.__code__.co_varnames})
        print("PREVIEW OK")
        print(json.dumps(preview, indent=2)[:2000])
    except Exception as e:
        print("PREVIEW ERROR:", repr(e))
        print("kwargs used:", {k:v for k,v in order_kwargs.items()
                               if k in getattr(et.preview_equity_order, '__code__', type('x', (), {'co_varnames': ()})) .co_varnames})
        sys.exit(3)

    if not args.place:
        print("\n(add --place to actually submit the order)")
        return

    # 4) PLACE (try the most likely function names)
    placed = None
    errors = []
    for fn_name in ("place_equity_order","place_order"):
        fn = getattr(et, fn_name, None)
        if not callable(fn):
            continue
        try:
            used = {k:v for k,v in order_kwargs.items() if k in fn.__code__.co_varnames}
            placed = fn(**used)
            print(f"PLACE OK via {fn_name}")
            print(json.dumps(placed, indent=2)[:2000])
            return
        except Exception as e:
            errors.append((fn_name, repr(e)))
            continue

    print("PLACE ERROR:")
    for name, err in errors:
        print(" ", name, "->", err)
    print("If you have a different place function, please share its name/signature (dir(etrade_service)).")

if __name__ == "__main__":
    main()
