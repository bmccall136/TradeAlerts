from services.realized_service import insert_realized_trade
g = insert_realized_trade(r"C:\TradeAlerts\live.db","TEST",1,100,101,"2025-12-28","2025-12-28","SELL")
print("gain=", g)
