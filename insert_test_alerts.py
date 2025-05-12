import sqlite3
from datetime import datetime

DB = 'alerts_clean.db'

tests = [
    ('TEST','Test Corp','BUY',99,123.45,'prime'),
    ('TEST2','Test Sharpshooter','BUY',98,67.89,'sharpshooter'),
    ('TEST3','Test Opportunist','BUY',97,45.67,'opportunist'),
]

conn = sqlite3.connect(DB)
c = conn.cursor()

for sym, name, signal, conf, price, ttype in tests:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''
        INSERT INTO alerts
        (symbol,name,signal,confidence,price,timestamp,type,sparkline,triggers,vwap)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (sym,name,signal,conf,price,ts,ttype,'','',price))

conn.commit()
conn.close()
print("Inserted test alerts.")
