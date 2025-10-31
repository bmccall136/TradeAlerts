# C:\TradeAlerts\why_no_buys_v3.py
import logging, json, os
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from importlib import import_module

def to_dict(x):
    if isinstance(x, dict):
        return x
    try:
        from requests import Response
        if isinstance(x, Response):
            try:
                return x.json()
            except Exception:
                try:
                    return json.loads(x.text or "")
                except Exception:
                    return {}
    except Exception:
        pass
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {}
    if isinstance(x, (list, tuple)) and x and isinstance(x[-1], dict):
        return x[-1]
    return {}

def dig(d,*p,default=None):
    cur=d
    for k in p:
        if not isinstance(cur,dict): return default
        cur = cur.get(k)
    return cur if cur is not None else default

def as_float(v):
    try:
        if v is None: return 0.0
        if isinstance(v,(int,float)): return float(v)
        if isinstance(v,str):
            return float(v.replace("$","").replace(",","").strip())
    except Exception:
        return 0.0
    return 0.0

def as_money(x): return f"${x:,.2f}"

def resolve_key(et):
    env = os.environ.get("ACCOUNT_ID_KEY") or os.environ.get("ETRADE_ACCOUNT_ID_KEY")
    if env: return env
    for fn in ("get_primary_account","get_default_account","primary_account"):
        f = getattr(et, fn, None)
        if callable(f):
            try:
                d=f()
                if isinstance(d,dict):
                    for k in ("accountIdKey","account_id_key","key"):
                        if d.get(k): return d[k]
            except Exception: pass
    f = getattr(et,"list_accounts",None)
    if callable(f):
        try:
            arr=f()
            if isinstance(arr,dict):
                arr = arr.get("Accounts") or arr.get("accounts") or arr.get("data") or []
            for row in arr:
                if isinstance(row,dict) and row.get("accountIdKey"):
                    return row["accountIdKey"]
        except Exception: pass
    return None

def main():
    et = None
    for n in ("services.etrade_service","etrade_service"):
        try:
            et = import_module(n); break
        except Exception: pass
    if not et:
        logging.info("etrade_service not importable.")
        return

    ak = resolve_key(et)
    logging.info("[A] account key: %s", ak or "NONE")

    b = {}
    for fn in ("get_balances","get_balance","balance","fetch_balances"):
        f = getattr(et, fn, None)
        if callable(f):
            try:
                raw = f(ak) if ak else f()
                b = to_dict(raw)
                if b: break
            except Exception as e:
                logging.info("balances.%s failed: %s", fn, e)

    if not isinstance(b, dict):
        logging.info("balances not dict; type=%s", type(b).__name__)
        return

    # Try multiple ATT shapes
    att_candidates = [
        ("availableToTrade",),
        ("cashAvailableForInvestment",),
        ("Cash","availableToTrade"),
        ("Cash","cashAvailableForInvestment"),
        ("BalanceResponse","availableToTrade"),
        ("BalanceResponse","cashAvailableForInvestment"),
        ("Computed","availableToTrade"),
    ]
    vals = []
    for p in att_candidates:
        vals.append(as_float(dig(b,*p)))
    att = max(vals) if vals else 0.0

    pv  = 0.0
    for p in [("positionsValue",),("BalanceResponse","positionsValue"),("Computed","positionsValue")]:
        pv = max(pv, as_float(dig(b,*p)))

    bp  = 0.0
    for p in [("buyingPower",),("BalanceResponse","buyingPower"),("Computed","buyingPower")]:
        bp = max(bp, as_float(dig(b,*p)))

    sc  = 0.0
    for p in [("settledCash",),("BalanceResponse","settledCash"),("Cash","settledCash"),("Computed","settledCash")]:
        sc = max(sc, as_float(dig(b,*p)))

    logging.info("[B] parsed: AvailableToTrade=%s | BuyingPower=%s | SettledCash=%s | PositionsValue=%s",
                 as_money(att), as_money(bp), as_money(sc), as_money(pv))
    present = [key for key in (
        "availableToTrade","cashAvailableForInvestment","buyingPower","settledCash","positionsValue"
    ) if dig(b,key) is not None]
    logging.info("[C] top-level present: %s", ", ".join(present) or "<none>")
    # quick hint which source was used
    logging.info("[D] ATT sources tried (max used): %s", " > ".join(".".join(p) for p in att_candidates))

if __name__ == "__main__":
    main()
