import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Target the bad block where sym/qty got injected between cur.execute( and the SQL string.
# We'll replace ONLY that local block.
pat = re.compile(
    r'(?P<indent>\s*)cur\.execute\(\s*\n'
    r'(?P=indent)\s*sym\s*=\s*str\(t\.get\("symbol",\s*""\)\s*or\s*""\)\.strip\(\)\.upper\(\)\s*\n'
    r'(?P=indent)\s*if\s+not\s+sym:\s*\n'
    r'(?P=indent)\s*    continue\s*\n'
    r'(?P=indent)\s*qty\s*=\s*float\(t\.get\("qty",\s*0\.0\)\s*or\s*0\.0\)\s*\n'
    r'(?P=indent)\s*if\s+qty\s*<=\s*0:\s*\n'
    r'(?P=indent)\s*    continue\s*\n'
    r'(?P=indent)\s*"INSERT INTO realized_trades \(symbol, action, qty, close_date, gain\) VALUES \(\?, \?, \?, \?, \?\)",\s*\n'
    r'(?P=indent)\s*\(sym,\s*action,\s*qty,\s*dt_et\.isoformat\(\),\s*pl\),\s*\n'
    r'(?P=indent)\s*\)\s*',
    re.IGNORECASE
)

def repl(m):
    indent = m.group("indent")
    # Put sym/qty above cur.execute, then execute normally
    return (
        f'{indent}sym = str(t.get("symbol", "") or "").strip().upper()\n'
        f'{indent}if not sym:\n'
        f'{indent}    continue\n'
        f'{indent}qty = float(t.get("qty", 0.0) or 0.0)\n'
        f'{indent}if qty <= 0:\n'
        f'{indent}    continue\n'
        f'{indent}cur.execute(\n'
        f'{indent}    "INSERT INTO realized_trades (symbol, action, qty, close_date, gain) VALUES (?, ?, ?, ?, ?)",\n'
        f'{indent}    (sym, action, qty, dt_et.isoformat(), pl),\n'
        f'{indent})\n'
    )

src2, n = pat.subn(repl, src)
if n != 1:
    raise SystemExit(f"ERROR: expected to repair 1 bad cur.execute block, repaired {n}")

p.write_text(src2, encoding="utf-8")
print("OK repaired injected block")
