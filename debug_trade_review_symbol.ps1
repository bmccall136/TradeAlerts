param(
  [Parameter(Mandatory=$true)]
  [string]$Symbol,

  [string]$Root = "C:\TradeAlerts",
  [string]$Logs = "C:\TradeAlerts\logs",
  [string]$Db   = "C:\TradeAlerts\live.db"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Symbol = $Symbol.Trim().ToUpper()
if (-not (Test-Path -LiteralPath $Db)) { throw "DB not found: $Db" }
if (-not (Test-Path -LiteralPath $Logs)) { throw "Logs not found: $Logs" }

$py = @"
import os, glob, csv, sqlite3
from datetime import datetime

SYM = os.environ["SYM"].strip().upper()
DB  = os.environ["DB"]
LOG = os.environ["LOG"]

def latest_row_from_csv(pattern, sym, time_key_candidates):
    files = sorted(glob.glob(os.path.join(LOG, pattern)), key=os.path.getmtime, reverse=True)
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8", newline="") as f:
                r = csv.DictReader(f)
                rows = [row for row in r if (row.get("symbol","").strip().upper() == sym)]
                if not rows:
                    continue
                # prefer last row in that file
                row = rows[-1]
                ts = None
                for k in time_key_candidates:
                    v = (row.get(k) or "").strip()
                    if v:
                        ts = v
                        break
                return fp, ts, row
        except Exception:
            continue
    return None, None, None

print(f"=== TRADE REVIEW DEBUG: {SYM} ===")
print(f"DB   : {DB}")
print(f"LOGS : {LOG}")

# --- DB checks ---
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

print("\n-- live.db: realized_trades (latest 5 for symbol) --")
try:
    cur.execute("SELECT * FROM realized_trades WHERE symbol=? ORDER BY close_date DESC LIMIT 5", (SYM,))
    rows = cur.fetchall()
    if not rows:
        print("NONE")
    else:
        for r in rows:
            d = dict(r)
            print({k:d.get(k) for k in ("symbol","qty","open_date","close_date","open_price","close_price","gain") if k in d})
except Exception as e:
    print("ERROR querying realized_trades:", e)

print("\n-- live.db: position_opened (latest 5 for symbol, if table exists) --")
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='position_opened'")
    if cur.fetchone():
        cur.execute("SELECT * FROM position_opened WHERE symbol=? ORDER BY opened_utc DESC LIMIT 5", (SYM,))
        rows = cur.fetchall()
        if not rows:
            print("NONE")
        else:
            for r in rows:
                d = dict(r)
                # show likely columns if present
                keys = ["symbol","opened_utc","opened_et","qty","price"]
                print({k:d.get(k) for k in keys if k in d})
    else:
        print("TABLE NOT PRESENT")
except Exception as e:
    print("ERROR querying position_opened:", e)

con.close()

# --- CSV checks ---
print("\n-- logs: latest BUY trigger row (triggers_*.csv) --")
buy_fp, buy_ts, buy_row = latest_row_from_csv("triggers_*.csv", SYM, ["time_et","ts_et","ts_utc"])
if not buy_fp:
    print("NONE")
else:
    print("file:", os.path.basename(buy_fp))
    print("ts  :", buy_ts)
    # print a compact subset
    keep = ["time_et","ts_et","symbol","price","signals_pretty","vwap","macd","rsi","bb","vol_spike","news"]
    print({k:buy_row.get(k) for k in keep if k in buy_row})

print("\n-- logs: latest SELL trigger row (sell_triggers_*.csv) --")
sell_fp, sell_ts, sell_row = latest_row_from_csv("sell_triggers_*.csv", SYM, ["time_et","ts_et","ts_utc"])
if not sell_fp:
    print("NONE")
else:
    print("file:", os.path.basename(sell_fp))
    print("ts  :", sell_ts)
    keep = ["time_et","ts_et","symbol","event","action","reason","trigger","pl_pct","hold_min","status","err"]
    print({k:sell_row.get(k) for k in keep if k in sell_row})

print("\n=== BEST ANCHORS (what Trade Review should use) ===")
print("BUY anchor :", buy_ts)
print("SELL anchor:", sell_ts)
"@

$env:SYM = $Symbol
$env:DB  = $Db
$env:LOG = $Logs

# Use your venv python if you prefer; this uses whatever "python" resolves to.
$py | python
