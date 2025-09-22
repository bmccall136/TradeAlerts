
"""
mrna_sell_diag.py — Diagnose why MRNA shows "no free long shares", optionally cancel sells, and optionally place a market sell.

USAGE (run from your C:\TradeAlerts folder):
  py mrna_sell_diag.py                   # show positions & open orders for MRNA
  py mrna_sell_diag.py --cancel          # cancel ALL open SELL orders for MRNA (incl. stops/limits/GTC)
  py mrna_sell_diag.py --sell            # market sell the full *available* long quantity of MRNA
  py mrna_sell_diag.py --sell  5         # market sell exactly 5 shares
  py mrna_sell_diag.py --cancel --sell   # cancel any blocking sells, then sell the available qty

Notes:
- Requires your existing services/etrade_service.py helper.
- Only sells long stock positions (not options). Fractional shares are skipped by default unless --allow-fractional.
"""

import sys, json, argparse, time
from typing import Any, Dict, List

# Ensure we can import your local services package when run from anywhere
import os
HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from services import etrade_service as et
except Exception as e:
    print("[FATAL] Could not import services.etrade_service:", e)
    print("Make sure you run this from your TradeAlerts root (C:\\TradeAlerts) and that 'services' is a package.")
    sys.exit(1)

SYMBOL = "MRNA"

def _float(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d

def _fmt(o: Any) -> str:
    try:
        return json.dumps(o, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(o)

def get_primary_acct_id() -> str:
    # Prefer an existing helper if you have one; otherwise, pull first margin/cash account
    try:
        acct = et.get_primary_account_id()
        if acct:
            return str(acct)
    except Exception:
        pass

    # Fallback: list accounts and pick the first
    try:
        accts = et.list_accounts()
        if isinstance(accts, (list, tuple)) and accts:
            # choose the first brokerage account
            for a in accts:
                if str(a.get("accountMode","")).upper() in ("BROKERAGE","MARGIN","CASH") or a.get("accountId"):
                    return str(a.get("accountId") or a.get("accountIdKey") or a.get("accountId"))
            # or just first
            return str(accts[0].get("accountId") or accts[0].get("accountIdKey") or accts[0])
    except Exception as e:
        print("[WARN] list_accounts failed:", e)

    raise RuntimeError("Could not determine account id")

def list_open_orders_for_symbol(account_id: str, symbol: str) -> List[Dict[str, Any]]:
    try:
        orders = et.list_open_orders(account_id)
    except Exception as e:
        print("[WARN] list_open_orders failed:", e)
        return []
    out = []
    for o in orders or []:
        try:
            syms = []
            action = (o.get("orderAction") or o.get("orderType") or "").upper()
            # E*TRADE payloads often nest "OrderDetail" with "Instrument" entries.
            legs = o.get("orderDetail") or o.get("orderDetails") or []
            if isinstance(legs, dict):
                legs = [legs]
            for leg in legs:
                inst = leg.get("instrument") or leg.get("Instrument") or []
                if isinstance(inst, dict):
                    inst = [inst]
                for i in inst:
                    s = (i.get("symbol") or i.get("productSymbol") or i.get("symbolDescription") or "").upper()
                    if s:
                        syms.append(s)
            if symbol.upper() in syms:
                out.append(o)
        except Exception:
            pass
    return out

def get_position_row(account_id: str, symbol: str) -> Dict[str, Any] | None:
    try:
        pos = et.get_positions(account_id)
    except Exception as e:
        print("[WARN] get_positions failed:", e)
        return None
    # Normalize
    items = pos or []
    # Some wrappers return {"positions":[{...}]}
    if isinstance(items, dict):
        for k in ("positions","Position","securitiesAccountPositions","data","items"):
            if k in items and isinstance(items[k], list):
                items = items[k]
                break
    for p in items:
        try:
            sym = (p.get("symbol") or p.get("Product",{}).get("symbol") or p.get("securitySymbol","")).upper()
            if sym == symbol.upper():
                return p
        except Exception:
            continue
    return None

def qty_available_from_position(p: Dict[str, Any]) -> float:
    # Consider typical E*TRADE fields we have seen across payloads
    for k in ("quantityAvailable", "qtyAvailable", "availableQuantity", "available"):
        v = p.get(k)
        if v is not None:
            return _float(v, 0.0)
    # Some structures put it under 'lots' aggregation
    lots = p.get("lots") or p.get("lot") or []
    if isinstance(lots, dict):
        lots = [lots]
    avail = 0.0
    for lot in lots:
        for k in ("availableQty","qtyAvailable","quantityAvailable"):
            v = lot.get(k)
            if v is not None:
                avail += _float(v, 0.0)
    if avail > 0:
        return avail
    # Fallback to total quantity (may be fully reserved by orders)
    for k in ("longQuantity","quantity","qty","positionQuantity"):
        v = p.get(k)
        if v is not None:
            return max(0.0, _float(v, 0.0))
    return 0.0

def cancel_all_sell_orders_for_symbol(account_id: str, symbol: str) -> int:
    orders = list_open_orders_for_symbol(account_id, symbol)
    n = 0
    for o in orders:
        try:
            oid = o.get("orderId") or o.get("orderIdString") or o.get("orderNumber") or o.get("orderid")
            # Be conservative: only cancel SELL-side orders
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            if "SELL" in side and oid:
                print(f"  - cancel {oid} {side}")
                try:
                    et.cancel_order(account_id, oid)
                    n += 1
                except Exception as e:
                    print("    cancel failed:", e)
        except Exception as e:
            print("  - skip order (parse error):", e)
    return n

def place_market_sell(account_id: str, symbol: str, qty: float, allow_fractional: bool=False) -> Dict[str, Any]:
    if qty <= 0:
        raise ValueError("qty must be > 0")
    if not allow_fractional:
        qty = int(qty)  # floor to whole shares
        if qty == 0:
            raise ValueError("available quantity is fractional; rerun with --allow-fractional to proceed")
    print(f"[SELL] Placing market sell: {symbol} qty={qty}")
    # Prefer a helper if you have one:
    try:
        return et.sell_market(account_id, symbol, qty)
    except Exception:
        # Fallback to place_order style if used in your codebase
        try:
            return et.place_order(account_id, action="SELL", symbol=symbol, quantity=qty, orderType="MARKET")
        except Exception as e:
            raise

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cancel", action="store_true", help="cancel ALL open SELL orders for MRNA")
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="place a market sell (auto = use available qty)")
    ap.add_argument("--allow-fractional", action="store_true", help="permit fractional share sells")
    args = ap.parse_args()

    acct = get_primary_acct_id()
    print("[DBG] account_id:", acct)

    pos = get_position_row(acct, SYMBOL)
    if not pos:
        print(f"[INFO] No position found for {SYMBOL}. You likely hold 0 shares.")
    else:
        print("[POS] Raw:")
        print(_fmt(pos))
        avail = qty_available_from_position(pos)
        total = _float(pos.get("longQuantity") or pos.get("quantity") or pos.get("qty") or 0)
        print(f"[POS] {SYMBOL}: total={total}  available={avail}")

    open_sells = list_open_orders_for_symbol(acct, SYMBOL)
    if open_sells:
        print(f"[ORD] {len(open_sells)} open order(s) for {SYMBOL}:")
        for o in open_sells:
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            oid  = o.get("orderId") or o.get("orderNumber") or o.get("orderIdString") or o.get("orderid")
            st   = (o.get("orderStatus") or o.get("status") or "").upper()
            print(f"  - {oid} {side} status={st}")
    else:
        print("[ORD] No open orders for", SYMBOL)

    if args.cancel:
        n = cancel_all_sell_orders_for_symbol(acct, SYMBOL)
        print(f"[CANCEL] Attempted to cancel {n} SELL order(s) for {SYMBOL}.")
        # Refresh available after cancel
        time.sleep(1.0)
        pos = get_position_row(acct, SYMBOL) or {}
        avail = qty_available_from_position(pos) if pos else 0.0
        print(f"[POS] post-cancel available={avail}")

    if args.sell is not None:
        if args.sell == "__AUTO__":
            if not pos:
                print("[SELL] Aborting: no position found.")
                return
            avail = qty_available_from_position(pos)
            if avail <= 0:
                print("[SELL] Aborting: available qty is 0 (still reserved by an order?). Try --cancel.")
                return
            resp = place_market_sell(acct, SYMBOL, avail, allow_fractional=args.allow_fractional)
        else:
            qty = _float(args.sell, -1.0)
            if qty <= 0:
                print("[SELL] Invalid qty; use a positive number.")
                return
            resp = place_market_sell(acct, SYMBOL, qty, allow_fractional=args.allow_fractional)
        print("[SELL] Response:")
        print(_fmt(resp))

if __name__ == "__main__":
    main()
