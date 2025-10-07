# test_auth_flow.py
from etrade_auth import get_authenticated_session

print("🔍 Starting OAuth test…")
session = get_authenticated_session()
print("✅ OAuth succeeded. Session:", session)
