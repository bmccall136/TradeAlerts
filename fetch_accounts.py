# fetch_accounts.py

import logging
import pprint
import sys

# ensure your project package imports correctly
sys.path.insert(0, ".")

from services.market_service import client

logger = logging.getLogger("debug")
logger.setLevel(logging.DEBUG)

resp = client.session.get(
    f"{client.base_url}/v1/accounts/list.json", params={"needBalances": "true"}
)

print("Status:", resp.status_code)
print("Body (first 200 chars):", resp.text[:200])
try:
    data = resp.json()
    pprint.pprint(data)
except ValueError:
    print("Response was not valid JSON")
