import json
import os

from dotenv import load_dotenv

# Load .env so NEWSAPI_KEY is available
load_dotenv()

try:
    # Your project style: services/news_service.py
    from services.news_service import fetch_latest_headlines
except ModuleNotFoundError as e:
    print("ERROR: Could not import services.news_service")
    print("Make sure you have C:\\TradeAlerts\\services\\news_service.py")
    raise

def main() -> None:
    symbol = "SPY"  # test symbol

    print("CWD:", os.getcwd())
    print("NEWSAPI_KEY present:", bool(os.getenv("NEWSAPI_KEY")))

    headlines = fetch_latest_headlines(symbol, count=5)
    print(f"Got {len(headlines)} headlines for {symbol}:")
    print(json.dumps(headlines, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
