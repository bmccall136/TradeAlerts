# _pos_peek2.py
import os, json
os.environ.setdefault("ETRADE_ENV","production")
from services import etrade_service as et

def L(x): return x if isinstance(x, list) else ([] if x is None else [x])

def main():
    try:
        acct = et._primary_account_id()
    except Exception:
        accs = et.get_accounts()
        acct = next(((a.get("accountIdKey") or a.get("accountKey") or a.get("accountId"))
                     for a in L((accs.get("Accounts") or {}).get("Account")) if a), None)
    try:
        pos = et.get_positions(acct)
    except TypeError:
        pos = et.get_positions()

    pr = (pos or {}).get("PortfolioResponse") or {}
    rows = []
    for ap in L(pr.get("AccountPortfolio")):
        for p in L(ap.get("Position") or ap.get("position") or ap.get("Positions") or ap.get("positions")):
            prod = p.get("Product") or {}
            sym  = (prod.get("symbol") or "").strip().upper()
            desc = (p.get("symbolDescription") or "").strip()
            qty  = p.get("quantity") or p.get("longQty") or p.get("longQuantity") or 0
            rows.append({"sym": sym, "desc": desc, "qty": qty, "prod_keys": sorted(list(prod.keys()))})
    print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    main()
