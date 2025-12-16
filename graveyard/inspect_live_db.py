import os
import re
import sqlite3
import sys

db = r"C:\TradeAlerts\live.db"
if not os.path.exists(db):
    print(f"[!] DB not found: {db}")
    sys.exit(1)
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
tables = [
    r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")
]
print("Tables:", tables)

REALIZED = re.compile(r"(realized.*p?l|pnl_?realized|realized|rlzd)", re.I)
TIME = re.compile(r"(closed|filled|execut.*|time|date|created).*", re.I)


def cols(t):
    return [r[1] for r in con.execute(f"PRAGMA table_info({t})")]


def sum_table(t, start=None, end=None):
    rcols = [c for c in cols(t) if REALIZED.fullmatch(c) or REALIZED.search(c)]
    if not rcols:
        return None
    rcol = rcols[0]
    tcols = [c for c in cols(t) if TIME.fullmatch(c) or TIME.search(c)]
    if tcols:
        tcol = tcols[0]
        q = f"SELECT COALESCE(SUM({rcol}),0.0) FROM {t} WHERE {rcol} IS NOT NULL"
        params = []
        if start is not None:
            q += f" AND {tcol} >= ?"
            params.append(start)
        if end is not None:
            q += f" AND {tcol} <  ?"
            params.append(end)
        return float(con.execute(q, params).fetchone()[0] or 0.0)
    else:
        # no timestamps -> only usable for ALL
        if start or end:
            return 0.0
        return float(
            con.execute(
                f"SELECT COALESCE(SUM({rcol}),0.0) FROM {t} WHERE {rcol} IS NOT NULL"
            ).fetchone()[0]
            or 0.0
        )


def bucket_sum(start=None, end=None):
    # search priority
    order = ["realized", "pnl", "trades", "trade_log", "executions", "fills", "orders", "ledger"]
    order = [t for t in order if t in tables] + [t for t in tables if t not in order]
    for t in order:
        v = sum_table(t, start, end)
        if v is not None:
            return t, v
    return None, None


from datetime import UTC, datetime, timedelta

now = datetime.now(UTC)
monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
last_monday = monday - timedelta(days=7)
first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

label, all_sum = bucket_sum(None, None)
print(f"ALL  -> table={label} sum={all_sum:.2f}")

label, week_sum = bucket_sum(monday.isoformat(), None)
print(f"WEEK -> table={label} sum={week_sum:.2f}")

label, lastw_sum = bucket_sum(last_monday.isoformat(), monday.isoformat())
print(f"LASTW-> table={label} sum={lastw_sum:.2f}")

label, month_sum = bucket_sum(first_of_month.isoformat(), None)
print(f"MONTH-> table={label} sum={month_sum:.2f}")
