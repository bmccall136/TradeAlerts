# services/signal_service.py

import pandas as pd
import logging

# Turn on debug logging for this module
logging.basicConfig(level=logging.DEBUG)


def compute_buy_triggers(df: pd.DataFrame) -> list:
    """
    Return buy triggers:
      - 'prime'         : all 4 conditions pass
      - 'sharpshooter'  : any 3 of 4 pass
      - [] otherwise
    """
    logging.debug("🔍 compute_buy_triggers called; last rows:\n%s", df.tail(3))

    triggers = []
    passes = 0

    # 1) Green candle: Close > Open
    if df['Close'].iat[-1] > df['Open'].iat[-1]:
        passes += 1
        logging.debug("   ✅ Condition1 (green candle)")

    # 2) Volume spike: current volume > 1.5× avg of last 20
    avg_vol = df['Volume'].tail(20).mean() or 0
    if df['Volume'].iat[-1] > 1.5 * avg_vol:
        passes += 1
        logging.debug("   ✅ Condition2 (volume spike)")

    # 3) Price above 20-period SMA
    sma20 = df['Close'].rolling(window=20).mean().iat[-1]
    if df['Close'].iat[-1] > sma20:
        passes += 1
        logging.debug("   ✅ Condition3 (above SMA20)")

    # 4) Momentum: Close > Close 3 bars ago
    if len(df) >= 4 and df['Close'].iat[-1] > df['Close'].iat[-4]:
        passes += 1
        logging.debug("   ✅ Condition4 (positive momentum)")

    # Evaluate passes
    if passes == 4:
        triggers.append('prime')
    elif passes == 3:
        triggers.append('sharpshooter')

    logging.debug("✅ compute_buy_triggers returning: %s (passes=%d)", triggers, passes)
    return triggers


def compute_sell_triggers(df: pd.DataFrame) -> list:
    """
    Return ['sell'] if exit conditions met:
      - red candle and
      - price below 20-period SMA
    """
    logging.debug("🔍 compute_sell_triggers called; last rows:\n%s", df.tail(3))

    triggers = []

    # Red candle?
    red_candle = df['Close'].iat[-1] < df['Open'].iat[-1]
    # Below SMA20?
    sma20 = df['Close'].rolling(window=20).mean().iat[-1]
    below_sma = df['Close'].iat[-1] < sma20

    if red_candle and below_sma:
        triggers.append('sell')
        logging.debug("   ✅ Sell condition met (red candle & below SMA20)")
    else:
        logging.debug("   ℹ️ Sell condition not met (red_candle=%s, below_sma=%s)",
                      red_candle, below_sma)

    logging.debug("✅ compute_sell_triggers returning: %s", triggers)
    return triggers
