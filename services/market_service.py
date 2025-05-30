import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import yfinance as yf
from services.etrade_service import fetch_etrade_quote
from services.alert_service import generate_sparkline
import pandas as pd

def get_symbols(simulation=False):
    """Fetch S&P 500 symbols from Wikipedia (live), or fallback to local file."""
    if simulation:
        filename = 'sim_symbols.txt'
        try:
            with open(filename, 'r') as f:
                syms = [line.strip() for line in f if line.strip()]
            return syms
        except Exception as e:
            logger.error(f"Could not load symbols from {filename}: {e}")
            return []

    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        table = pd.read_html(url)
        syms = table[0]['Symbol'].tolist()
        # Clean up symbols (remove periods for compatibility if needed)
        syms = [s.replace('.', '-') for s in syms]
        logger.info(f"Fetched {len(syms)} S&P 500 symbols from Wikipedia.")
        return syms
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 symbols from Wikipedia: {e}")
        # Fallback to file
        filename = 'sp500_symbols.txt'
        try:
            with open(filename, 'r') as f:
                syms = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(syms)} S&P 500 symbols from {filename}.")
            return syms
        except Exception as e:
            logger.error(f"Could not load symbols from {filename}: {e}")
            return []

logger = logging.getLogger(__name__)

def get_symbols(simulation=False):
    # You can customize this as needed; here's a simple version:
    filename = 'sp500_symbols.txt'
    if simulation:
        filename = 'sim_symbols.txt'
    try:
        with open(filename, 'r') as f:
            syms = [line.strip() for line in f if line.strip()]
        return syms
    except Excetion as e:
        logger.error(f"Could not load symbols from {filename}: {e}")
        return []

def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    def do_fetch():
        return yf.Ticker(sym).history(period=period, interval=interval)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(do_fetch)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            logger.error(f"[TIMEOUT] Yahoo fetch for {sym} timed out after {timeout}s!")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Yahoo fetch for {sym} failed: {e}")
            return None

from datetime import datetime
from services.alert_service import insert_alert

def analyze_symbol(sym):
    df = fetch_data_with_timeout(sym)
    if df is None or df.empty:
        logger.error(f"→ [SKIP] {sym}: Yahoo Finance returned no data (period=1d)")
        return None

    # --- Fetch E*TRADE price and log it ---
    try:
        etrade_price = fetch_etrade_quote(sym)
    except Exception as e:
        logger.error(f"→ [SKIP] {sym}: E*TRADE fetch exception: {e}")
        return None

    if not etrade_price or etrade_price == 0.0:
        logger.error(f"→ [SKIP] {sym}: E*TRADE returned no last price!")
        return None

    logger.info(f"{sym}: E*TRADE last price = ${etrade_price:.2f}")

    # --- Calculate technical indicators from Yahoo data ---
    macd_line, sig_line = calculate_macd(df['Close'])
    rsi_series = compute_rsi(df['Close'])
    vol = df['Volume'].iloc[-1]
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    bb_up, bb_mid, bb_dn = compute_bollinger(df['Close'])

    triggers = []
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        triggers.append('MACD 🚀')
    if rsi_series.iloc[-1] < 30:
        triggers.append('RSI 📉')
    if vol > avg_vol:
        triggers.append('VOL 🔊')
    if df['Close'].iloc[-1] > bb_up.iloc[-1] or df['Close'].iloc[-1] < bb_dn.iloc[-1]:
        triggers.append('BB 📈')
    logger.info(f"→ {sym}: {triggers}")

    if len(triggers) < 3:
        logger.info(f"→{sym}: Not enough triggers ({len(triggers)}), skipping alert.")
        return None

    # --- Generate sparkline (as SVG or string as before) ---
    spark = generate_sparkline(df['Close'].tolist())

    alert = {
        'symbol': sym,
        'price': etrade_price,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name': '',         # You can fill this if you want to fetch company name
        'vwap': 0,          # Replace if you calculate vwap
        'vwap_diff': 0,     # Replace if you calculate vwap diff
        'sparkline': spark,
        'triggers': ",".join(triggers)
    }

    logger.info(f"→{sym}: Alert ready, inserting to DB.")
    insert_alert(**alert)
    return alert

# You may need to import or define your indicator functions here:
def calculate_macd(close):
    # Dummy placeholder - replace with your real MACD function
    import pandas as pd
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    sig_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, sig_line

def compute_rsi(close, window=14):
    # Dummy placeholder - replace with your real RSI function
    import pandas as pd
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_bollinger(close, window=20, num_std=2):
    # Dummy placeholder - replace with your real Bollinger function
    import pandas as pd
    rolling_mean = close.rolling(window).mean()
    rolling_std = close.rolling(window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, rolling_mean, lower_band
