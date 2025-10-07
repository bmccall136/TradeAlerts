# services/label_config.py

# mapping of settings values to human-friendly labels used in backtest (and simulation) forms

timeframe_labels = {
    "1d": "1 Day",
    "1h": "1 Hour",
    "15m": "15 Minutes",
}

sma_length_labels = {10: "10", 20: "20", 50: "50", 100: "100"}

rsi_len_labels = {7: "7", 14: "14", 21: "21"}
rsi_overbought_labels = {70: "70", 80: "80", 90: "90"}
rsi_oversold_labels = {30: "30", 20: "20", 10: "10"}

macd_fast_labels = {5: "5", 12: "12", 26: "26"}
macd_slow_labels = {12: "12", 26: "26", 52: "52"}
macd_signal_labels = {5: "5", 9: "9", 12: "12"}

bb_length_labels = {10: "10", 20: "20", 50: "50"}
bb_std_labels = {1.5: "1.5", 2.0: "2.0", 2.5: "2.5"}

vol_mult_labels = {1.0: "1×", 2.0: "2×", 3.0: "3×"}

# your template expects vwap_labels, so alias it here:
vwap_labels = {0.0: "0", 0.5: "0.5", 1.0: "1.0"}

trailing_stop_pct_labels = {0.01: "1%", 0.02: "2%", 0.05: "5%", 0.10: "10%"}

sell_after_days_labels = {
    None: "None",
    1: "1 Day",
    5: "5 Days",
    10: "10 Days",
}
