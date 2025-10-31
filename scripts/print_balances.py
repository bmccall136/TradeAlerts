# scripts/print_balances.py
import os
import sys
sys.path.insert(0, r"C:\TradeAlerts")  # safety

from services.broker import get_broker

b = get_broker("LIVE")
summary = b.get_account_summary() or {}
ui = summary.get("ui", {}) or {}

def fmt(x):
    try: return f"${float(x):.2f}"
    except: return "—"

print("=== E*TRADE (LIVE) — Balances ===")
print("Buying Power           :", fmt(ui.get("buying_power")))
print("Available to Withdraw  :", fmt(ui.get("available_to_withdraw")))
print("Available to Trade     :", fmt(ui.get("available_to_trade")))
print("Settled Cash           :", fmt(ui.get("settled_cash")))
print("Net Account Value (NAV):", fmt(ui.get("nav")))
print("Positions Value        :", fmt(ui.get("positions_value")))
