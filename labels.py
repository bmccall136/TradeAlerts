# labels.py

# ─── SMA options ───
sma_labels = {
    10: "Short SMA (10)",
    20: "Standard SMA (20)",
    50: "Long SMA (50)",
}

# ─── RSI options ───
rsi_len_labels = {
    7:  "RSI (7)",
    14: "Std RSI (14)",
    21: "RSI (21)",
}
rsi_ob_labels = {70: "70", 80: "80", 90: "90"}
rsi_os_labels = {30: "30", 20: "20", 10: "10"}

# ─── MACD options ───
macd_fast_labels   = {12: "Fast EMA (12)", 9: "Fast EMA (9)", 6: "Fast EMA (6)"}
macd_slow_labels   = {26: "Slow EMA (26)", 21: "Slow EMA (21)", 18: "Slow EMA (18)"}
macd_signal_labels = {9: "Signal SMA (9)", 12: "Signal SMA (12)"}

# ─── Bollinger Bands ───
bb_length_labels = {20: "BB Length 20", 10: "BB Length 10", 50: "BB Length 50"}
bb_std_labels    = {2.0: "2σ", 2.5: "2.5σ", 3.0: "3σ"}

# ─── Volume & VWAP ───
vol_mult_labels = {2.0: "High ×2", 1.5: "High ×1.5", 1.0: "High ×1.0"}
vwap_labels     = {0.5: "≥ $0.5",   1.0: "≥ $1.0"}
