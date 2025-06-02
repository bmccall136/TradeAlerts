
import sqlite3
from services.market_service import get_realtime_price
from datetime import datetime

SIM_DB = 'C:/TradeAlerts/simulation.db'  # Absolute path for Windows

def get_cash():
    with sqlite3.connect(SIM_DB) as conn:
        result = conn.execute("SELECT cash_balance FROM account LIMIT 1").fetchone()
        return result[0] if result else 0

def get_realized_pl():
    with sqlite3.connect(SIM_DB) as conn:
        result = conn.execute("SELECT realized_pl FROM state LIMIT 1").fetchone()
        return result[0] if result else 0

def get_holdings():
    with sqlite3.connect(SIM_DB) as conn:
        rows = conn.execute("SELECT symbol, qty, avg_cost FROM holdings").fetchall()

    holdings = []
    for symbol, qty, avg_cost in rows:
        last_price = get_realtime_price(symbol) or 0
        prev_price = 0  # Placeholder, replace with real historic price if needed
        change = last_price - prev_price
        change_percent = ((change / prev_price) * 100) if prev_price else 0
        value = qty * last_price
        day_gain = change * qty
        total_gain = (last_price - avg_cost) * qty
        total_gain_percent = ((last_price - avg_cost) / avg_cost) * 100 if avg_cost else 0
        holdings.append({
            'symbol': symbol,
            'qty': qty,
            'avg_cost': avg_cost,
            'last_price': last_price,
            'change': change,
            'change_percent': change_percent,
            'value': value,
            'day_gain': day_gain,
            'total_gain': total_gain,
            'total_gain_percent': total_gain_percent
        })
    return holdings

def get_trades():
    with sqlite3.connect(SIM_DB) as conn:
        rows = conn.execute("SELECT timestamp, symbol, action, quantity, price FROM trades ORDER BY id DESC").fetchall()

    trades = []
    for ts, sym, action, qty, price in rows:
        pl = None
        if action.upper() == 'SELL':
            with sqlite3.connect(SIM_DB) as conn2:
                row = conn2.execute("SELECT avg_cost FROM holdings WHERE symbol = ?", (sym,)).fetchone()
            if row:
                avg_cost = row[0]
                pl = (price - avg_cost) * qty
        trades.append({
            'timestamp': ts,
            'symbol': sym,
            'action': action,
            'quantity': qty,
            'price': price,
            'pl': pl
        })
    return trades

def get_open_value():
    return sum(h['value'] for h in get_holdings())

import os
def buy_stock(symbol, qty, price):
    print("🛒 buy_stock() called")
    print(f"   Symbol: {symbol}, Qty: {qty}, Price: {price}")
    print("📁 Using DB Path:", os.path.abspath(SIM_DB))
    total_cost = price * qty
    timestamp = datetime.now().strftime('%H:%M:%S')
    name = "Unknown"  # Default fallback

    with sqlite3.connect(SIM_DB) as conn:
        cur = conn.cursor()
        cash = get_cash()
        if total_cost > cash:
            raise ValueError("Not enough cash to complete purchase")

        cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        if row:
            existing_qty, existing_cost = row
            new_qty = existing_qty + qty
            new_avg = ((existing_qty * existing_cost) + (qty * price)) / new_qty
            cur.execute("UPDATE holdings SET qty = ?, avg_cost = ?, last_price = ? WHERE symbol = ?",
                        (new_qty, new_avg, price, symbol))
        else:
            cur.execute("INSERT INTO holdings (symbol, qty, avg_cost, last_price) VALUES (?, ?, ?, ?)",
                        (symbol, qty, price, price))

        new_cash = cash - total_cost
        cur.execute("UPDATE account SET cash_balance = ?", (new_cash,))
        cur.execute("INSERT INTO trades (timestamp, symbol, action, quantity, price, name) VALUES (?, ?, ?, ?, ?, ?)",
                    (timestamp, symbol, 'BUY', qty, price, name))
        conn.commit()
        print('✅ Commit successful')
