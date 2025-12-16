# _pos_peek.py
import os, json
os.environ.setdefault("ETRADE_ENV","production")
from services import etrade_service as et

def as_list(x): return x if isinstance(x, list) else ([] if x is None else [x])

def main():
    try:
        acct = et._primary_account_id()
    except Exception:
        accs = et.get_accounts()
        acct = next(((a.get("accountIdKey") or a.get("accountKey") or a.get("accountId"))
                     for a in as_list((accs.get("Accounts") or {}).get("Account")) if a), None)
    try:
        pos = et.get_positions(acct)
    except TypeError:
        pos = et.get_positions()

    pr = (pos or {}).get("PortfolioResponse") or {}
    rows = []
    for ap in as_list(pr.get("AccountPortfolio")):
        for p in as_list(ap.get("Position") or ap.get("position") or ap.get("Positions") or ap.get("positions")):
            inst = p.get("instrument") or p.get("Instrument") or {}
            rows.append({
                "p_keys": sorted(list(p.keys())),
                "inst_keys": sorted(list(inst.keys())),
                "inst": inst
            })
            if len(rows) >= 5:
                break
        if rows: break

    print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    main()
