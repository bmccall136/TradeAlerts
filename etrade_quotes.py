
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ETRADE_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")
BASE_URL = "https://api.etrade.com"

def get_intraday_history(symbol):
    # Simulated E*TRADE intraday response
    # Replace this with real API logic as needed
    # This version returns timestamps and close prices for demo
    try:
        # Simulated response for now
        now = datetime.now()
        timestamps = [(now - timedelta(minutes=i)).strftime("%H:%M") for i in range(5, 0, -1)]
        close_prices = [round(100 + i * 0.5, 2) for i in range(5)]
        return {"timestamp": timestamps, "close": close_prices}
    except Exception as e:
        print(f"Failed to fetch E*TRADE intraday data: {e}")
        return None
