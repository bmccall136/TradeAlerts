import json
import os

from dotenv import load_dotenv

load_dotenv("etrade.env")

print(f"🔑 CONSUMER_KEY: {os.getenv('PRODUCTION_CONSUMER_KEY')}")
print(f"🔑 CONSUMER_SECRET: {os.getenv('PRODUCTION_CONSUMER_SECRET')}")

try:
    with open("etrade_tokens.json") as f:
        tokens = json.load(f)
    print(f"🪪 ACCESS_TOKEN: {tokens.get('access_token')}")
    print(f"🪪 ACCESS_TOKEN_SECRET: {tokens.get('access_token_secret')}")
except Exception as e:
    print(f"❌ Failed loading etrade_tokens.json: {e}")
