# test_env.py
import os
from dotenv import load_dotenv

load_dotenv("etrade.env")

print(f"ETRADE_ENV: {os.getenv('ETRADE_ENV')}")
print(f"ETRADE_API_KEY: {os.getenv('ETRADE_API_KEY')}")
