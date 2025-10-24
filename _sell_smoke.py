# _sell_smoke.py
import os, json, sys, traceback
os.environ.setdefault("ETRADE_ENV", "production")

from services import etrade_service as et  # your wrapper

def as_list(x): return x if isinstance(x, list) else ([] if x is None else [x])

def get_acct_key():
    # prefer your helper if present
    try:
        return et._primary_account_id()
    except Exception:
        pass
    accs = et.get_accounts()
    acct_list = as_list((accs.get("Accounts") or {}).get("Account"))
    for a in acct_list:
        k = a.get("accountIdKey") or a.get("accountKey") or a.get("accountId")
        if k: return k

def get_positions(acct_key):
    try:
        return et.get_positions(acct_key)
    except TypeError:
        return et.get_positions()

def flatten_positions(pos):
    pr = (pos or {}).get("PortfolioResponse") or {}
    out = []
    for ap in as_list(pr.get("AccountPortfolio")):
        positions = ap.get("Position") or ap.get("position") or ap.get("Positions") or ap.get("positions")
        for p in as_list(positions):
            inst = p.get("instrument") or p.get("Instrument") or {}
            sym  = (inst.get("symbol") or p.get("symbol") or "").upper().strip()
            qty  = (
                p.get("longQty") or p.get("longQuantity")
                or p.get("qty") or p.get("quantity")
                or p.get("positionQty") or p.get("positionQuantity") or 0
            )
            try:
                qf = float(qty or 0)
            except Exception:
                continue
            out.append({"sym": sym, "qty_float": qf, "qty_whole": int(qf)})
    return out

def preview_sell(acct_key, sym, qty):
    # Try keyword signature first; fall back to positional
    try:
        return et.preview_equity_order(
            account_id_key=acct_key,
            symbol=sym,
            quantity=qty,
            orderAction="SELL",
            priceType="MARKET",
        )
    except TypeError:
        return et.preview_equity_order(acct_key, sym, qty, orderAction="SELL", priceType="MARKET")

def main():
    acct = get_acct_key()
    print("[ACCT]", acct)

    pos = get_positions(acct)
    flat = flatten_positions(pos)
    print("[POSITIONS]", json.dumps(flat, indent=2))

    # pick first with at least 1 whole share
    candidates = [r for r in flat if r["sym"] and r["qty_whole"] >= 1]
    if not candidates:
        print("[RESULT] No whole-share holdings. (All fractional or empty.) Nothing to preview.")
        return 0

    sym = candidates[0]["sym"]
    qty = 1  # minimal safe test
    print(f"[PREVIEW] SELL MARKET {sym} x{qty}")
    try:
        resp = preview_sell(acct, sym, qty)
        print("RAW PREVIEW:", json.dumps(resp, indent=2))
        err = (resp or {}).get("Error") or (resp or {}).get("error")
        if err:
            print("[BROKER ERROR]", err.get("code"), "-", err.get("message"))
            return 1
        print("[OK] Preview succeeded.")
        return 0
    except Exception as e:
        print("[EXC]", e); traceback.print_exc()
        return 2

if __name__ == "__main__":
    sys.exit(main())
