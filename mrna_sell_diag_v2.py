
"""
mrna_sell_diag_v2.py — Robust MRNA "no free shares" diagnosis with broad E*TRADE helper compatibility.

USAGE (from C:\TradeAlerts):
  py mrna_sell_diag_v2.py                 # print account id, position totals/available, and open SELL orders
  py mrna_sell_diag_v2.py --cancel        # cancel ALL open SELL orders for MRNA
  py mrna_sell_diag_v2.py --sell          # market sell available qty (whole shares by default)
  py mrna_sell_diag_v2.py --sell 5        # market sell exactly 5 shares
  py mrna_sell_diag_v2.py --sell --allow-fractional

If account id detection fails, run with --debug to see which functions/attrs exist in services.etrade_service.
"""

import sys, json, argparse, time, os, inspect
from typing import Any, Dict, List

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from services import etrade_service as et
except Exception as e:
    print("[FATAL] Could not import services.etrade_service:", e)
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

def _has(name: str) -> bool:
    return hasattr(et, name) and callable(getattr(et, name, None))

def _attr(name: str):
    return getattr(et, name) if hasattr(et, name) else None

def get_primary_acct_id(debug: bool=False) -> str:
    # Try common function names
    for fn in ("get_primary_account_id","get_primary_acct_id","get_account_id","primary_account_id","default_account_id"):
        if _has(fn):
            try:
                acct = str(getattr(et, fn)())
                if acct and acct.lower() not in ("none","null","0"):
                    if debug: print(f"[DBG] acct via {fn} -> {acct}")
                    return acct
            except Exception as e:
                if debug: print(f"[DBG] {fn}() failed: {e}")

    # Try constants
    for const in ("PRIMARY_ACCOUNT_ID","ACCOUNT_ID","DEFAULT_ACCOUNT_ID","ACCOUNTID","AcctId"):
        val = _attr(const)
        if isinstance(val, (str,int)):
            acct = str(val)
            if acct and acct.lower() not in ("none","null","0"):
                if debug: print(f"[DBG] acct via const {const} -> {acct}")
                return acct

    # Try listing accounts
    for fn in ("list_accounts","get_accounts","get_account_list","accounts"):
        if _has(fn):
            try:
                accts = getattr(et, fn)()
                if debug: print(f"[DBG] {fn}() -> type={type(accts).__name__}")
                if isinstance(accts, dict):
                    # heuristic: look for accountId-ish fields
                    for k in ("accounts","AccountList","items","data","accountList"):
                        if k in accts and isinstance(accts[k], list) and accts[k]:
                            first = accts[k][0]
                            for idk in ("accountId","accountIdKey","accountKey","id"):
                                aid = first.get(idk)
                                if aid:
                                    if debug: print(f"[DBG] acct via {fn}/{k}/{idk} -> {aid}")
                                    return str(aid)
                if isinstance(accts, (list,tuple)) and accts:
                    first = accts[0]
                    if isinstance(first, dict):
                        for idk in ("accountId","accountIdKey","accountKey","id"):
                            aid = first.get(idk)
                            if aid:
                                if debug: print(f"[DBG] acct via {fn}/list/{idk} -> {aid}")
                                return str(aid)
                    else:
                        # could just be a string id
                        if debug: print(f"[DBG] acct via {fn}/list[0] -> {first}")
                        return str(first)
            except Exception as e:
                if debug: print(f"[DBG] {fn}() failed: {e}")

    # Try pulling any overview that includes account id
    for fn in ("get_account_overview","account_overview","get_balance","get_balances","get_accounts_overview"):
        if _has(fn):
            try:
                ov = getattr(et, fn)()
                if debug: print(f"[DBG] {fn}() keys={list(ov.keys()) if isinstance(ov, dict) else type(ov)}")
                cand = None
                if isinstance(ov, dict):
                    for idk in ("accountId","accountIdKey","accountKey","id"):
                        if idk in ov:
                            cand = ov[idk]; break
                    if not cand:
                        for k in ov.values():
                            if isinstance(k, dict):
                                for idk in ("accountId","accountIdKey","accountKey","id"):
                                    if idk in k:
                                        cand = k[idk]; break
                            if cand: break
                if cand:
                    if debug: print(f"[DBG] acct via {fn} -> {cand}")
                    return str(cand)
            except Exception as e:
                if debug: print(f"[DBG] {fn}() failed: {e}")

    raise RuntimeError("Could not determine account id")

def list_open_orders_for_symbol(account_id: str, symbol: str) -> List[Dict[str, Any]]:
    # Try multiple variants
    orders = None
    for fn in ("list_open_orders","get_open_orders","open_orders","list_orders"):
        if _has(fn):
            try:
                sig = inspect.signature(getattr(et, fn))
                if len(sig.parameters) >= 1:
                    orders = getattr(et, fn)(account_id)
                else:
                    orders = getattr(et, fn)()
                break
            except Exception:
                continue
    if orders is None:
        return []

    out = []
    for o in orders or []:
        try:
            syms = []
            action = (o.get("orderAction") or o.get("orderType") or "").upper()
            legs = o.get("orderDetail") or o.get("orderDetails") or []
            if isinstance(legs, dict):
                legs = [legs]
            if not legs and "instrument" in o:
                legs = [o]  # sometimes instrument sits at top-level
            for leg in legs:
                inst = leg.get("instrument") or leg.get("Instrument") or []
                if isinstance(inst, dict):
                    inst = [inst]
                if not inst and "symbol" in leg:
                    inst = [leg]
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
    # Try multiple variants
    pos = None
    for fn in ("get_positions","list_positions","positions","get_portfolio"):
        if _has(fn):
            try:
                sig = inspect.signature(getattr(et, fn))
                if len(sig.parameters) >= 1:
                    pos = getattr(et, fn)(account_id)
                else:
                    pos = getattr(et, fn)()
                break
            except Exception:
                continue
    if pos is None:
        return None

    items = pos
    if isinstance(items, dict):
        for k in ("positions","Position","securitiesAccountPositions","data","items","portfolioPositions"):
            if k in items and isinstance(items[k], list):
                items = items[k]
                break
    if not isinstance(items, list):
        items = [items]

    for p in items:
        try:
            sym = (p.get("symbol") or p.get("Product",{}).get("symbol") or p.get("securitySymbol","")).upper()
            if sym == symbol.upper():
                return p
        except Exception:
            continue
    return None

def qty_available_from_position(p: Dict[str, Any]) -> float:
    for k in ("quantityAvailable", "qtyAvailable", "availableQuantity", "available"):
        v = p.get(k)
        if v is not None:
            return _float(v, 0.0)
    lots = p.get("lots") or p.get("lot") or []
    if isinstance(lots, dict): lots = [lots]
    avail = 0.0
    for lot in lots:
        for k in ("availableQty","qtyAvailable","quantityAvailable"):
            v = lot.get(k)
            if v is not None:
                avail += _float(v, 0.0)
    if avail > 0:
        return avail
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
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            if "SELL" in side and oid:
                print(f"  - cancel {oid} {side}")
                # Try cancel variants
                cancelled = False
                for fn in ("cancel_order","cancel","orders_cancel"):
                    if _has(fn):
                        try:
                            sig = inspect.signature(getattr(et, fn))
                            if len(sig.parameters) >= 2:
                                getattr(et, fn)(account_id, oid)
                            else:
                                getattr(et, fn)(oid)
                            cancelled = True
                            break
                        except Exception as e:
                            print("    cancel attempt failed via", fn, "->", e)
                if cancelled:
                    n += 1
        except Exception as e:
            print("  - skip order (parse error):", e)
    return n

def place_market_sell(account_id: str, symbol: str, qty: float, allow_fractional: bool=False) -> Dict[str, Any]:
    if qty <= 0:
        raise ValueError("qty must be > 0")
    if not allow_fractional:
        qty = int(qty)
        if qty == 0:
            raise ValueError("available quantity is fractional; rerun with --allow-fractional")

    for fn in ("sell_market","place_order","order_market_sell"):
        if _has(fn):
            try:
                if fn == "place_order":
                    return getattr(et, fn)(account_id, action="SELL", symbol=symbol, quantity=qty, orderType="MARKET")
                else:
                    return getattr(et, fn)(account_id, symbol, qty)
            except Exception as e:
                print(f"[WARN] {fn} failed: {e}")
                continue
    raise RuntimeError("No supported sell function found in etrade_service")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cancel", action="store_true", help="cancel ALL open SELL orders for MRNA")
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="place a market sell (auto = use available qty)")
    ap.add_argument("--allow-fractional", action="store_true", help="permit fractional share sells")
    ap.add_argument("--debug", action="store_true", help="print function/attr availability to help detect wiring")
    args = ap.parse_args()

    if args.debug:
        print("[DBG] etrade_service has:")
        names = [n for n in dir(et) if not n.startswith("_")]
        print("     ", ", ".join(sorted(names)))

    acct = get_primary_acct_id(debug=args.debug)
    print("[INFO] account_id:", acct)

    pos = get_position_row(acct, SYMBOL)
    if not pos:
        print(f"[INFO] No position found for {SYMBOL}. total=0, available=0")
        total = 0.0; avail = 0.0
    else:
        total = _float(pos.get("longQuantity") or pos.get("quantity") or pos.get("qty") or 0.0)
        avail = qty_available_from_position(pos)
        print("[POS] Raw:"); print(_fmt(pos))
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
        print("[SELL] Response:"); print(_fmt(resp))

if __name__ == "__main__":
    main()
