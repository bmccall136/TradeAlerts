import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import yfinance as yf
from services.etrade_service import fetch_etrade_quote
from services.alert_service import generate_sparkline, insert_alert
import pandas as pd
from datetime import datetime
# We no longer need compute_vwap_for_symbol here, since we’ll compute intraday VWAP directly
# from the OHLCV DataFrame.
# from services.chart_service import compute_vwap_for_symbol
from services.etrade_service import get_etrade_price

logger = logging.getLogger(__name__)


def get_symbols(simulation=False):
    """Fetch S&P 500 symbols from local file (or switch to Wikipedia scraping if desired)."""
    filename = 'sim_symbols.txt' if simulation else 'sp500_symbols.txt'
    try:
        with open(filename, 'r') as f:
            syms = [line.strip() for line in f if line.strip()]
        return syms
    except Exception as e:
        logger.error(f"Could not load symbols from {filename}: {e}")
        return []


def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    """
    Download OHLCV from Yahoo Finance asynchronously (to avoid blocking).
    """
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


def analyze_symbol(sym):
    """
    1) Grab 1d/5m bars from Yahoo  
    2) Grab E*TRADE last price  
    3) Grab company name via yfinance (.info['longName'])  
    4) Calculate MACD, RSI, Volume, Bollinger  
    5) Compute intraday VWAP + Diff  
    6) If ≥ 3 triggers (out of MACD, RSI, VOL, BB, VWAP), build a sparkline 
       and insert_alert(...)  
    """
    # 1) Download Yahoo data
    df = fetch_data_with_timeout(sym)
    if df is None or df.empty:
        logger.error(f"→ [SKIP] {sym}: Yahoo Finance returned no data.")
        return None

    # 2) Fetch latest price via E*TRADE
    try:
        etrade_price = fetch_etrade_quote(sym)
    except Exception as e:
        logger.error(f"→ [SKIP] {sym}: E*TRADE fetch exception: {e}")
        return None

    if not etrade_price or etrade_price == 0.0:
        logger.error(f"→ [SKIP] {sym}: E*TRADE returned no last price.")
        return None

    logger.info(f"{sym}: E*TRADE last price = ${etrade_price:.2f}")

    # 3) Fetch full company name via yfinance
    try:
        ticker = yf.Ticker(sym)
        info = ticker.info
        # Prefer longName; fallback to shortName; fallback to ticker itself
        company_name = info.get('longName') or info.get('shortName') or sym
    except Exception as e:
        logger.error(f"→ [WARN] {sym}: Failed to fetch company name: {e}")
        company_name = sym

    # 4) Compute indicators (MACD, RSI, Volume, Bollinger)
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

    # 5) Compute intraday VWAP + Diff
    # Calculate Typical Price = (High + Low + Close) / 3
    df['TypicalPrice'] = (df['High'] + df['Low'] + df['Close']) / 3
    # TPV = TypicalPrice * Volume
    df['TPV'] = df['TypicalPrice'] * df['Volume']
    # Cumulative TPV and cumulative Volume
    df['CumulativeTPV'] = df['TPV'].cumsum()
    df['CumulativeVol'] = df['Volume'].cumsum()
    # VWAP = cumulative(TPV) / cumulative(Volume)
    df['VWAP'] = df['CumulativeTPV'] / df['CumulativeVol']

    latest_vwap = df['VWAP'].iloc[-1]
    vwap_diff_value = etrade_price - latest_vwap
    logger.info(f"{sym}: Intraday VWAP = ${latest_vwap:.2f}, Diff = ${vwap_diff_value:.2f}")
    # Only append a VWAP trigger if price is above VWAP
    if vwap_diff_value > 0:
        triggers.append('VWAP+Diff 🚀')

    # 6) Check if we have at least three triggers
    logger.info(f"→ {sym}: {triggers}")
    if len(triggers) < 3:
        logger.info(f"→ {sym}: Not enough triggers ({len(triggers)}), skipping alert.")
        return None

    # 7) Generate sparkline
    spark_svg = generate_sparkline(df['Close'].tolist())

    # 8) Build alert payload and insert into DB
    alert_payload = {
        'symbol': sym,
        'price': etrade_price,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name': company_name,
        'vwap': round(latest_vwap, 2),
        'vwap_diff': round(vwap_diff_value, 2),
        'triggers': ",".join(triggers),
        'sparkline': spark_svg
    }
    insert_alert(**alert_payload)


# ---------- Indicator Helpers (unchanged) ----------

def calculate_macd(close):
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    sig_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, sig_line


def compute_rsi(close, window=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_bollinger(close, window=20, num_std=2):
    rolling_mean = close.rolling(window).mean()
    rolling_std = close.rolling(window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, rolling_mean, lower_band


def get_realtime_price(symbol):
    try:
        quote = get_etrade_price(symbol)
        return float(quote) if quote is not None else None
    except Exception as e:
        print(f"❌ Failed to fetch price for {symbol}: {e}")
        return None
