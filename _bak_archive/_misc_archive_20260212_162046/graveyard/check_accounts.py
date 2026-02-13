# check_accounts.py
import pprint
from services.etrade_service import get_oauth_session, account_identity

pp = pprint.PrettyPrinter(indent=2, width=100)

def list_accounts(sess):
    r = sess.get("https://api.etrade.com/v1/accounts/list.json", timeout=15)
    r.raise_for_status()
    j = r.json() or {}
    accounts = (
        j.get("AccountListResponse", {}).get("Accounts", {}).get("Account", [])
    ) or j.get("accounts", [])
    if isinstance(accounts, dict):
        accounts = [accounts]
    # normalize
    out = []
    for a in accounts:
        out.append({
            "accountId": (a.get("accountId") or a.get("accountIdValue") or "").strip(),
            "accountIdKey": (a.get("accountIdKey") or a.get("accountIdKeyValue") or "").strip(),
            "desc": (a.get("accountDesc") or a.get("displayName") or a.get("accountTypeDesc") or "").strip(),
            "type": (a.get("accountType") or "").strip(),
        })
    return out

def get_balance(sess, account_key):
    # Standard balances endpoint mirrors your orders URL shape
    url = f"https://api.etrade.com/v1/accounts/{account_key}/balance.json"
    r = sess.get(url, timeout=15)
    r.raise_for_status()
    j = r.json() or {}
    # E*TRADE returns a few variants; try common nests
    bal = (
        j.get("BalanceResponse")
        or j.get("balanceResponse")
        or j
    )
    return bal

def main():
    sess = get_oauth_session()
    ident = account_identity()  # what your app currently selects
    print("=== App-selected account ===")
    pp.pprint(ident)

    accts = list_accounts(sess)
    print("\n=== All accounts (from list.json) ===")
    pp.pprint(accts)

    print("\n=== Balances per account ===")
    for a in accts:
        key = a["accountIdKey"]
        try:
            bal = get_balance(sess, key)
        except Exception as e:
            print(f"\n--- {a['desc']} ({key}) ---")
            print("ERROR fetching balances:", e)
            continue

        # pull the fields we care about (many names map to same idea)
        fields = {}
        for k in [
            "cashBuyingPower",
            "cashAvailableForWithdrawal",
            "settledCash",
            "netAccountValue",
            "marginBuyingPower",
            "cashBalance",
            "fundsWithheld",
            "fundsOnHold",
        ]:
            if k in bal:
                fields[k] = bal.get(k)

        print(f"\n--- {a['desc']} ({key}) ---")
        pp.pprint(fields)

if __name__ == "__main__":
    main()
