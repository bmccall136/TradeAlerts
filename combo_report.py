import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

DB = r"C:\TradeAlerts\live.db"

LOOKBACK_DAYS = 30
TRIGGER_LOOKBACK_SEC = 1800   # 30 min
OPEN_MATCH_SEC = 86400        # 24 hr
MIN_TRADES_PER_COMBO = 2

def parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def normalize_combo(signals_pretty):
    if not signals_pretty:
        return ("<none>", [])

    parts = [p.strip() for p in str(signals_pretty).split(",") if p.strip()]
    norm = []

    for p in parts:
        u = p.upper()
        if "MACD" in u:
            norm.append("macd")
        elif "VWAP" in u:
            norm.append("vwap")
        elif "ADX" in u:
            norm.append("adx")
        elif "PRICE>SMA(50)" in u or "SMA50" in u or "PRICE > SMA" in u:
            norm.append("sma50")
        elif "SMA20" in u:
            norm.append("sma20")
        elif "SMA" in u:
            norm.append("sma")
        elif "VOL" in u:
            norm.append("vol")
        elif "RSI" in u:
            norm.append("rsi")
        elif "BB" in u or "BOLL" in u:
            norm.append("bb")
        elif "ATR" in u:
            norm.append("atr")
        else:
            norm.append(p.lower())

    uniq = sorted(set(norm))
    combo = "|".join(uniq) if uniq else "<none>"
    return combo, uniq

def load_rows(conn):
    cur = conn.cursor()

    since_dt = datetime.now() - timedelta(days=LOOKBACK_DAYS)
    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")

    buys = cur.execute("""
        SELECT id, ts_et, ts_utc, symbol, price, qty, action
        FROM trades
        WHERE action='BUY' AND ts_et >= ?
        ORDER BY ts_et
    """, (since_str,)).fetchall()

    triggers = cur.execute("""
        SELECT id, ts_utc, symbol, side, stage, source, price, signals_pretty, notes
        FROM trigger_fires
        WHERE side='BUY'
        ORDER BY ts_utc
    """).fetchall()

    realized = cur.execute("""
        SELECT id, symbol, action, qty, open_date, close_date, gain, gain_pct, price_sold, cost_share
        FROM realized_trades
        WHERE action='SELL'
        ORDER BY close_date
    """).fetchall()

    return buys, triggers, realized

def find_trigger_for_buy(buy, symbol_triggers):
    buy_dt = parse_dt(buy[1])
    if not buy_dt:
        return None

    symbol = buy[3]
    buy_epoch = int(buy_dt.timestamp())

    best = None
    best_delta = None

    for tr in symbol_triggers.get(symbol, []):
        tr_epoch = tr[1]
        if tr_epoch is None:
            continue
        delta = buy_epoch - int(tr_epoch)
        if 0 <= delta <= TRIGGER_LOOKBACK_SEC:
            if best is None or delta < best_delta:
                best = tr
                best_delta = delta

    return best

def find_realized_for_buy(buy, symbol_realized):
    buy_dt = parse_dt(buy[1])
    if not buy_dt:
        return None

    symbol = buy[3]
    best = None
    best_delta = None

    for rz in symbol_realized.get(symbol, []):
        open_dt = parse_dt(rz[4])
        if not open_dt:
            continue
        delta = abs((open_dt - buy_dt).total_seconds())
        if delta <= OPEN_MATCH_SEC:
            if best is None or delta < best_delta:
                best = rz
                best_delta = delta

    return best

def pct_from_realized(rz):
    gain_pct = rz[7]
    if gain_pct is not None:
        return float(gain_pct)

    price_sold = rz[8]
    cost_share = rz[9]
    try:
        if price_sold is not None and cost_share not in (None, 0):
            return ((float(price_sold) - float(cost_share)) / float(cost_share)) * 100.0
    except Exception:
        pass
    return None

def main():
    conn = sqlite3.connect(DB)
    buys, triggers, realized = load_rows(conn)
    conn.close()

    symbol_triggers = defaultdict(list)
    for tr in triggers:
        symbol_triggers[tr[2]].append(tr)

    symbol_realized = defaultdict(list)
    for rz in realized:
        symbol_realized[rz[1]].append(rz)

    combo_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "net_gain": 0.0, "pct_sum": 0.0, "pct_n": 0})
    indicator_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "net_gain": 0.0, "pct_sum": 0.0, "pct_n": 0})

    matched_rows = []

    for buy in buys:
        tr = find_trigger_for_buy(buy, symbol_triggers)
        rz = find_realized_for_buy(buy, symbol_realized)

        if tr is None or rz is None:
            continue

        combo, indicators = normalize_combo(tr[7])
        gain = float(rz[6] or 0.0)
        pct = pct_from_realized(rz)

        s = combo_stats[combo]
        s["trades"] += 1
        s["net_gain"] += gain
        if gain > 0:
            s["wins"] += 1
        elif gain < 0:
            s["losses"] += 1
        if pct is not None:
            s["pct_sum"] += pct
            s["pct_n"] += 1

        for ind in indicators:
            si = indicator_stats[ind]
            si["trades"] += 1
            si["net_gain"] += gain
            if gain > 0:
                si["wins"] += 1
            elif gain < 0:
                si["losses"] += 1
            if pct is not None:
                si["pct_sum"] += pct
                si["pct_n"] += 1

        matched_rows.append({
            "symbol": buy[3],
            "buy_ts": buy[1],
            "combo": combo,
            "gain": gain,
            "gain_pct": pct,
            "signals_pretty": tr[7],
        })

    print(f"\nMatched trades: {len(matched_rows)}")
    print(f"Lookback days: {LOOKBACK_DAYS}")
    print(f"Trigger lookback sec: {TRIGGER_LOOKBACK_SEC}")
    print(f"Open match sec: {OPEN_MATCH_SEC}")

    print("\n=== COMBO REPORT ===")
    print(f"{'Combo':45} {'Trades':>6} {'Wins':>5} {'Loss':>5} {'WinRate':>8} {'AvgPct':>8} {'NetGain':>10}")
    combo_rows = []
    for combo, s in combo_stats.items():
        if s["trades"] < MIN_TRADES_PER_COMBO:
            continue
        wr = (s["wins"] / s["trades"] * 100.0) if s["trades"] else 0.0
        avgpct = (s["pct_sum"] / s["pct_n"]) if s["pct_n"] else 0.0
        combo_rows.append((avgpct, combo, s, wr))
    combo_rows.sort(key=lambda x: (x[0], x[2]["net_gain"]), reverse=True)

    for avgpct, combo, s, wr in combo_rows:
        print(f"{combo[:45]:45} {s['trades']:6d} {s['wins']:5d} {s['losses']:5d} {wr:7.1f}% {avgpct:8.2f} {s['net_gain']:10.2f}")

    print("\n=== INDICATOR REPORT ===")
    print(f"{'Indicator':15} {'Trades':>6} {'Wins':>5} {'Loss':>5} {'WinRate':>8} {'AvgPct':>8} {'NetGain':>10}")
    ind_rows = []
    for ind, s in indicator_stats.items():
        wr = (s["wins"] / s["trades"] * 100.0) if s["trades"] else 0.0
        avgpct = (s["pct_sum"] / s["pct_n"]) if s["pct_n"] else 0.0
        ind_rows.append((avgpct, ind, s, wr))
    ind_rows.sort(key=lambda x: (x[0], x[2]["net_gain"]), reverse=True)

    for avgpct, ind, s, wr in ind_rows:
        print(f"{ind[:15]:15} {s['trades']:6d} {s['wins']:5d} {s['losses']:5d} {wr:7.1f}% {avgpct:8.2f} {s['net_gain']:10.2f}")

    print("\n=== SAMPLE MATCHES ===")
    for r in matched_rows[:25]:
        gp = "" if r["gain_pct"] is None else f"{r['gain_pct']:.2f}%"
        print(f"{r['buy_ts']}  {r['symbol']:6}  {r['gain']:8.2f}  {gp:>8}  {r['combo']}")

if __name__ == "__main__":
    main()