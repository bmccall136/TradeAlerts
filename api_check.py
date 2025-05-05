import requests
from authlib.integrations.requests_client import OAuth1Session

# Manually load .env file
def load_env(filepath):
    env_vars = {}
    with open(filepath) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                env_vars[key] = value
    return env_vars

# Load credentials
env = load_env("etrade.env")

consumer_key = env.get("ETRADE_API_KEY")
consumer_secret = env.get("ETRADE_API_SECRET")
oauth_token = env.get("OAUTH_TOKEN")
oauth_token_secret = env.get("OAUTH_TOKEN_SECRET")
env_mode = env.get("ETRADE_ENV", "sandbox")

# Print what we loaded
print(f"Consumer Key: {consumer_key}")
print(f"Consumer Secret: {consumer_secret}")
print(f"OAuth Token: {oauth_token}")
print(f"OAuth Token Secret: {oauth_token_secret}")
print(f"Environment: {env_mode}")

# Check for missing
if not all([consumer_key, consumer_secret, oauth_token, oauth_token_secret]):
    raise ValueError("Missing credentials or tokens!")

# Set API URL
if env_mode == "production":
    base_url = "https://api.etrade.com"
else:
    base_url = "https://apisb.etrade.com"

# Create OAuth1 session
session = OAuth1Session(
    client_id=consumer_key,
    client_secret=consumer_secret,
    token=oauth_token,
    token_secret=oauth_token_secret,
)

# Try hitting the accounts API
url = f"{base_url}/v1/accounts/list.json"

try:
    response = session.get(url)
    response.raise_for_status()
    print("✅ API connection successful!")
except Exception as e:
    print(f"❌ API connection failed: {e}")
