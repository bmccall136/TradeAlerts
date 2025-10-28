from services import etrade_service as et
import json

acct = getattr(et, "get_primary_account_id_key", lambda: None)() or "kW8LbkuGisPCK9Ey7C8iWA"
print("acct:", acct)

try:
    data = et.get_account_summary(acct)
    print("SUMMARY:")
    print(json.dumps(data, indent=2))
except Exception as e:
    print("BALANCE ERROR:", e)
