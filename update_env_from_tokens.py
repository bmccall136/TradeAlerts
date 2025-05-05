import json
import os
import subprocess
from dotenv import load_dotenv

ENV_FILE = "etrade.env"
TOKENS_FILE = "etrade_tokens.json"

def load_env_tokens():
    if not os.path.exists(ENV_FILE):
        return None, None
    load_dotenv(ENV_FILE)
    return os.getenv("ACCESS_TOKEN"), os.getenv("ACCESS_TOKEN_SECRET")

def load_json_tokens():
    if not os.path.exists(TOKENS_FILE):
        return None, None
    with open(TOKENS_FILE) as f:
        data = json.load(f)
        return data.get("oauth_token"), data.get("oauth_token_secret")

def write_updated_env(oauth_token, oauth_token_secret):
    with open(ENV_FILE, "r") as f:
        lines = f.readlines()
    with open(ENV_FILE, "w") as f:
        for line in lines:
            if line.startswith("ACCESS_TOKEN="):
                f.write(f"ACCESS_TOKEN={oauth_token}\n")
            elif line.startswith("ACCESS_TOKEN_SECRET="):
                f.write(f"ACCESS_TOKEN_SECRET={oauth_token_secret}\n")
            else:
                f.write(line)
    print("✅ Updated etrade.env with new access tokens.")

def main():
    env_token, env_secret = load_env_tokens()
    json_token, json_secret = load_json_tokens()

    if (env_token != json_token) or (env_secret != json_secret):
        print("🔁 Tokens out of sync. Launching auth_helper.py to refresh...")
        subprocess.run(["python", "auth_helper.py"])
        json_token, json_secret = load_json_tokens()
        if json_token and json_secret:
            write_updated_env(json_token, json_secret)
        else:
            print("❌ Failed to read new tokens after auth.")
    else:
        print("✅ Tokens already up to date.")

if __name__ == "__main__":
    main()