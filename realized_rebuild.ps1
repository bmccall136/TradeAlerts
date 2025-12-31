# C:\TradeAlerts\realized_rebuild.ps1
param(
  [Parameter(Mandatory=$true)][string]$CsvPath,
  [string]$DbPath = "C:\TradeAlerts\live.db"
)

Write-Host "CSV: $CsvPath"
Write-Host " DB: $DbPath"
# 1) Ensure schema exists (safe)
python -c "import sqlite3; db=r'$DbPath'; con=sqlite3.connect(db); cur=con.cursor(); `
cur.execute('CREATE TABLE IF NOT EXISTS realized_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, action TEXT, qty REAL, close_date TEXT, gain REAL)'); `
cols=[r[1] for r in cur.execute('pragma table_info(realized_trades)').fetchall()]; `
('total_cost' not in cols) and cur.execute('ALTER TABLE realized_trades ADD COLUMN total_cost REAL'); `
('proceeds'   not in cols) and cur.execute('ALTER TABLE realized_trades ADD COLUMN proceeds REAL'); `
('gain_pct'   not in cols) and cur.execute('ALTER TABLE realized_trades ADD COLUMN gain_pct REAL'); `
con.commit(); con.close(); print('OK: schema ensured')"
# 2) Import (clear first)
python C:\TradeAlerts\import_realized_from_etrade_csv.py "$CsvPath" "$DbPath" --clear

# 3) Sanity
python -c "import sqlite3; con=sqlite3.connect(r'$DbPath'); cur=con.cursor();
print('rows',cur.execute('select count(*) from realized_trades').fetchone()[0]);
print('sum gain',cur.execute('select round(sum(gain),2) from realized_trades').fetchone()[0]);
print('sum cost',cur.execute('select round(sum(total_cost),2) from realized_trades').fetchone()[0]);
print('avg gain_pct',cur.execute('select round(avg(gain_pct),4) from realized_trades where total_cost>0').fetchone()[0]);
con.close()"
