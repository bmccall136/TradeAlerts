import pandas as pd

def calculate_indicators(df):
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]  # Get first column if it's a DataFrame

    # MACD
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Bollinger Bands
    ma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std()
    upper_bb = ma20 + (2 * std20)
    lower_bb = ma20 - (2 * std20)

    # Volume
    volume = df["Volume"]
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]
    volume_avg = volume.rolling(window=5).mean()

    if len(df) < 26:
        return None, 0, []

    # Force float conversion
    macd_val = macd.iloc[-1].item()
    signal_val = signal.iloc[-1].item()
    rsi_val = rsi.iloc[-1].item()
    price_val = close.iloc[-1].item()
    upper_bb_val = upper_bb.iloc[-1].item()
    lower_bb_val = lower_bb.iloc[-1].item()
    volume_val = volume.iloc[-1].item()
    volume_avg_val = volume_avg.iloc[-1].item()

    confidence = 0
    if macd_val > signal_val:
        confidence += 0.3
    if 40 < rsi_val < 70:
        confidence += 0.2
    if price_val > upper_bb_val:
        confidence += 0.2
    if volume_val > volume_avg_val:
        confidence += 0.3

    if confidence >= 0.7:
        return "BUY", round(confidence, 2), close.tail(15).tolist()
    elif confidence <= 0.2 and macd_val < signal_val and rsi_val < 30:
        return "SELL", round(1 - confidence, 2), close.tail(15).tolist()
    else:
        return None, round(confidence, 2), close.tail(15).tolist()